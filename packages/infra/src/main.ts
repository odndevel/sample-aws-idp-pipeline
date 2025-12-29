import { ApplicationStack } from './stacks/application-stack.js';
import { App } from ':idp-v2/common-constructs';

const app = new App();

new ApplicationStack(app, 'IDP-V2-Application', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION,
  },
});

app.synth();
