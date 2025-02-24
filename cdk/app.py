#!/usr/bin/env python3
import os
import aws_cdk as cdk

from python_cdk.lms_cdk_stack import LMSFullStack

# TODO pick this up from build pipeline env
stage = os.getenv('DEPLOY_STAGE', 'LOCAL')

if stage == 'LOCAL':
    env_props = cdk.Environment(account="000000000000", region="af-south-1")
elif stage == 'PROD':
    env_props = cdk.Environment(account="761018893754", region="af-south-1")
else:
    env_props = cdk.Environment(account="211125341265", region="af-south-1")

app = cdk.App()
LMSFullStack(app, 'Lms'+stage, env=env_props)

app.synth()
