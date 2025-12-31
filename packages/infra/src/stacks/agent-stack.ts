import { Stack, StackProps } from 'aws-cdk-lib';
import { Platform } from 'aws-cdk-lib/aws-ecr-assets';
import * as iam from 'aws-cdk-lib/aws-iam';
import { Construct } from 'constructs';
import * as path from 'path';
import {
  AgentRuntimeArtifact,
  ProtocolType,
  Runtime,
} from '@aws-cdk/aws-bedrock-agentcore-alpha';

export class AgentStack extends Stack {
  public readonly agentCoreRuntime: Runtime;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    const dockerImage = AgentRuntimeArtifact.fromAsset(
      path.resolve(process.cwd(), '../../packages/agents/idp-agent'),
      { platform: Platform.LINUX_ARM64 },
    );

    this.agentCoreRuntime = new Runtime(this, 'IdpAgentRuntime', {
      runtimeName: 'idp_agent_runtime',
      protocolConfiguration: ProtocolType.HTTP,
      agentRuntimeArtifact: dockerImage,
    });

    // Add Bedrock model invocation permissions
    this.agentCoreRuntime.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          'bedrock:InvokeModel',
          'bedrock:InvokeModelWithResponseStream',
        ],
        resources: ['*'],
      }),
    );
  }
}
