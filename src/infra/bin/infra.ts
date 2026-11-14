#!/usr/bin/env node
import { App, DefaultStackSynthesizer } from 'aws-cdk-lib/core';
import { InferenceStack } from '../lib/inference-stack';

const app = new App({
  defaultStackSynthesizer: new DefaultStackSynthesizer({
    dockerTagPrefix: 'wrime-sentiment-demo-',
  }),
});
new InferenceStack(app, 'WrimeInference', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: 'ap-northeast-1',
  },
});
