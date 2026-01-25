import { CfnOutput, Duration } from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import {
  Role,
  ServicePrincipal,
  PolicyStatement,
  ManagedPolicy,
} from 'aws-cdk-lib/aws-iam';
import { Bucket } from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as cloudwatchActions from 'aws-cdk-lib/aws-cloudwatch-actions';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as snsSubscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import { Construct } from 'constructs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export interface PaddleOcrEc2Props {
  /**
   * VPC to deploy EC2 instance
   */
  vpc: ec2.IVpc;
  /**
   * S3 bucket for model cache
   */
  modelBucket: Bucket;
  /**
   * S3 bucket for document storage
   */
  documentBucket: Bucket;
  /**
   * Path to inference server code directory
   */
  serverCodePath: string;
  /**
   * Idle timeout in minutes before stopping EC2
   * @default 10
   */
  idleTimeoutMinutes?: number;
}

export class PaddleOcrEc2 extends Construct {
  public readonly instance: ec2.Instance;
  public readonly instanceId: string;
  public readonly securityGroup: ec2.SecurityGroup;
  public readonly stopFunction: lambda.Function;

  constructor(scope: Construct, id: string, props: PaddleOcrEc2Props) {
    super(scope, id);

    const idleTimeoutMinutes = props.idleTimeoutMinutes ?? 10;

    // Security Group for EC2
    this.securityGroup = new ec2.SecurityGroup(this, 'SecurityGroup', {
      vpc: props.vpc,
      description: 'Security group for PaddleOCR EC2 instance',
      allowAllOutbound: true,
    });

    // Allow HTTP from within VPC (for Lambda to call)
    this.securityGroup.addIngressRule(
      ec2.Peer.ipv4(props.vpc.vpcCidrBlock),
      ec2.Port.tcp(8080),
      'Allow HTTP from VPC',
    );

    // IAM Role for EC2
    const ec2Role = new Role(this, 'InstanceRole', {
      assumedBy: new ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore'),
      ],
    });

    // S3 permissions
    props.modelBucket.grantReadWrite(ec2Role);
    props.documentBucket.grantRead(ec2Role);

    // CloudWatch Logs permissions
    ec2Role.addToPolicy(
      new PolicyStatement({
        actions: [
          'logs:CreateLogGroup',
          'logs:CreateLogStream',
          'logs:PutLogEvents',
        ],
        resources: ['*'],
      }),
    );

    // Upload inference server code to S3
    new s3deploy.BucketDeployment(this, 'ServerCodeDeployment', {
      sources: [s3deploy.Source.asset(props.serverCodePath)],
      destinationBucket: props.modelBucket,
      destinationKeyPrefix: 'paddleocr/server',
    });

    // User Data script for EC2 setup (direct installation)
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      '#!/bin/bash',
      'set -ex',
      '',
      '# Log output',
      'exec > >(tee /var/log/user-data.log) 2>&1',
      'echo "Starting user data script at $(date)"',
      '',
      '# Create app directory',
      'mkdir -p /opt/paddleocr',
      'mkdir -p /opt/paddleocr/models',
      '',
      '# Download inference server code from S3',
      `aws s3 cp s3://${props.modelBucket.bucketName}/paddleocr/server/inference_server.py /opt/paddleocr/`,
      '',
      '# Install system dependencies',
      'apt-get update',
      'apt-get install -y libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev',
      '',
      '# Install Python packages using conda (Deep Learning AMI has conda)',
      'source /opt/conda/etc/profile.d/conda.sh',
      'conda activate base',
      '',
      '# Install paddlepaddle-gpu (CUDA 11.8 compatible with Deep Learning AMI)',
      'pip install --upgrade pip',
      'pip install fastapi uvicorn boto3',
      'pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu118/',
      'pip install "paddleocr[all]" "paddlex[ocr]"',
      '# Downgrade numpy for PaddleOCR-VL compatibility',
      'pip install "numpy<2"',
      '',
      '# Create systemd service',
      'cat > /etc/systemd/system/paddleocr.service << EOF',
      '[Unit]',
      'Description=PaddleOCR Inference Server',
      'After=network.target',
      '',
      '[Service]',
      'Type=simple',
      'User=root',
      'WorkingDirectory=/opt/paddleocr',
      `Environment="MODEL_CACHE_BUCKET=${props.modelBucket.bucketName}"`,
      `Environment="DOCUMENT_BUCKET=${props.documentBucket.bucketName}"`,
      'Environment="PADDLEOCR_HOME=/opt/paddleocr/models/.paddleocr"',
      'Environment="PADDLEX_HOME=/opt/paddleocr/models/.paddlex"',
      'Environment="PATH=/opt/conda/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"',
      'ExecStart=/opt/conda/bin/python -m uvicorn inference_server:app --host 0.0.0.0 --port 8080',
      'Restart=always',
      'RestartSec=5',
      '',
      '[Install]',
      'WantedBy=multi-user.target',
      'EOF',
      '',
      '# Enable and start service',
      'systemctl daemon-reload',
      'systemctl enable paddleocr',
      'systemctl start paddleocr',
      '',
      'echo "User data script completed at $(date)"',
    );

    // EC2 Instance with NVIDIA GPU (g5.xlarge)
    this.instance = new ec2.Instance(this, 'Instance', {
      vpc: props.vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      instanceType: ec2.InstanceType.of(
        ec2.InstanceClass.G5,
        ec2.InstanceSize.XLARGE,
      ),
      // AWS Deep Learning AMI with CUDA pre-installed
      machineImage: ec2.MachineImage.lookup({
        name: 'Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.5.* (Ubuntu 22.04) *',
        owners: ['amazon'],
      }),
      securityGroup: this.securityGroup,
      role: ec2Role,
      userData,
      blockDevices: [
        {
          deviceName: '/dev/sda1',
          volume: ec2.BlockDeviceVolume.ebs(100, {
            volumeType: ec2.EbsDeviceVolumeType.GP3,
            encrypted: true,
            deleteOnTermination: false,
          }),
        },
      ],
    });

    this.instanceId = this.instance.instanceId;

    // Lambda to stop EC2 instance (triggered by CloudWatch Alarm via SNS)
    this.stopFunction = new lambda.Function(this, 'StopFunction', {
      functionName: 'idp-v2-paddleocr-ec2-stop',
      runtime: lambda.Runtime.PYTHON_3_14,
      handler: 'index.handler',
      timeout: Duration.minutes(2),
      code: lambda.Code.fromAsset(
        path.join(__dirname, '../functions/paddleocr/ec2-stop'),
      ),
      environment: {
        INSTANCE_ID: this.instance.instanceId,
      },
    });

    // Grant EC2 permissions to stop Lambda
    this.stopFunction.addToRolePolicy(
      new PolicyStatement({
        actions: ['ec2:DescribeInstances', 'ec2:StopInstances'],
        resources: ['*'],
      }),
    );

    // SNS Topic for CloudWatch Alarm
    const alarmTopic = new sns.Topic(this, 'IdleAlarmTopic', {
      topicName: 'paddleocr-ec2-idle-alarm',
    });

    // Subscribe stop Lambda to SNS
    alarmTopic.addSubscription(
      new snsSubscriptions.LambdaSubscription(this.stopFunction),
    );

    // CloudWatch Alarm for idle detection (CPU < 5% for N minutes)
    // Use 5-minute period to match EC2 basic monitoring interval
    const alarmPeriodMinutes = 5;
    const evaluationPeriods = Math.max(
      1,
      Math.floor(idleTimeoutMinutes / alarmPeriodMinutes),
    );
    const idleAlarm = new cloudwatch.Alarm(this, 'IdleAlarm', {
      alarmName: 'paddleocr-ec2-idle',
      alarmDescription: `Stop PaddleOCR EC2 when idle for ${evaluationPeriods * alarmPeriodMinutes} minutes`,
      metric: new cloudwatch.Metric({
        namespace: 'AWS/EC2',
        metricName: 'CPUUtilization',
        dimensionsMap: {
          InstanceId: this.instance.instanceId,
        },
        statistic: 'Average',
        period: Duration.minutes(alarmPeriodMinutes),
      }),
      threshold: 5,
      evaluationPeriods,
      comparisonOperator:
        cloudwatch.ComparisonOperator.LESS_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });

    idleAlarm.addAlarmAction(new cloudwatchActions.SnsAction(alarmTopic));

    // Outputs
    new CfnOutput(this, 'InstanceId', {
      value: this.instance.instanceId,
      description: 'PaddleOCR EC2 Instance ID',
    });
  }
}
