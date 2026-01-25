import { CfnOutput, Stack, StackProps } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as path from 'path';
import { fileURLToPath } from 'url';
import { SSM_KEYS } from ':idp-v2/common-constructs';
import { PaddleOcrEc2 } from '../constructs/index.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export class PaddleOcrStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // Get VPC from SSM (valueFromLookup for concrete value at synth time)
    const vpcId = StringParameter.valueFromLookup(this, SSM_KEYS.VPC_ID);
    const vpc = ec2.Vpc.fromLookup(this, 'Vpc', { vpcId });

    // Get model artifacts bucket from SSM
    const modelArtifactsBucketName = StringParameter.valueForStringParameter(
      this,
      SSM_KEYS.MODEL_ARTIFACTS_BUCKET_NAME,
    );

    const modelArtifactsBucket = s3.Bucket.fromBucketName(
      this,
      'ModelArtifactsBucket',
      modelArtifactsBucketName,
    );

    // Get document storage bucket from SSM
    const documentBucketName = StringParameter.valueForStringParameter(
      this,
      SSM_KEYS.DOCUMENT_STORAGE_BUCKET_NAME,
    );

    const documentBucket = s3.Bucket.fromBucketName(
      this,
      'DocumentBucket',
      documentBucketName,
    );

    // PaddleOCR EC2 Instance (g5.xlarge with GPU, direct installation)
    const paddleOcrEc2 = new PaddleOcrEc2(this, 'PaddleOcrEc2', {
      vpc,
      modelBucket: modelArtifactsBucket as s3.Bucket,
      documentBucket: documentBucket as s3.Bucket,
      serverCodePath: path.join(__dirname, '../functions/paddleocr/ec2-server'),
      idleTimeoutMinutes: 10,
    });

    // Store EC2 instance ID in SSM for WorkflowStack to reference
    new StringParameter(this, 'PaddleOcrEc2InstanceIdParam', {
      parameterName: SSM_KEYS.PADDLEOCR_EC2_INSTANCE_ID,
      stringValue: paddleOcrEc2.instanceId,
    });

    // Output for reference
    new CfnOutput(this, 'Ec2InstanceId', {
      value: paddleOcrEc2.instanceId,
      description: 'PaddleOCR EC2 Instance ID',
    });
  }
}
