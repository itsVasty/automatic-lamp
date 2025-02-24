import os

from aws_cdk import (
    aws_sns as sns,
    aws_sqs as sqs,
    aws_ssm as ssm,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_apigatewayv2 as apigateway,
    aws_apigatewayv2_integrations as integrations,
    aws_lambda_python_alpha as _python_lambda,
    Duration,
    CfnOutput, RemovalPolicy, Tags
)
from constructs import Construct

from python_cdk.string_utils import src_asset_excludes


class GitlabConnectConstruct(Construct):

    def __init__(self, scope: Construct, construct_id: str, events_topic: sns.Topic, events_table: dynamodb.Table,
                 send_email_queue: sqs.Queue,
                 send_matrix_queue: sqs.Queue,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.lms_functions = []

        # Function to handle Gitlab system hook events
        self.gitlab_api_handler = _python_lambda.PythonFunction(
            self, "lms-gitlab-callback-handler",
            function_name="lms-gitlab-callback-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="post",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="gitlab_connect/handlers/gitlab_systemhooks_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "SEND_EMAIL_QUEUE_NAME": send_email_queue.queue_name,
                "SEND_MATRIX_QUEUE_NAME": send_matrix_queue.queue_name,
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-gitlab-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(self.gitlab_api_handler).add("service", "lms-gitlab-service")
        self.lms_functions.append(self.gitlab_api_handler)
        # IAM permissions for SNS for router
        events_topic.grant_publish(self.gitlab_api_handler)
        send_email_queue.grant_send_messages(self.gitlab_api_handler)
        send_matrix_queue.grant_send_messages(self.gitlab_api_handler)
        self.set_ssm_permission_gitlab(self.gitlab_api_handler)

        # Create HTTP API for grading requests
        self.http_api = apigateway.HttpApi(self, "gitlab-callback-api")

        # Define the API Gateway integration with the 'router_function' Lambda
        gitlab_api_integration = integrations.HttpLambdaIntegration(
            'gitlab-http-integration',
            handler=self.gitlab_api_handler
        )

        # Define the API Gateway route and associate it with the integration
        post_gitlab_routes = self.http_api.add_routes(
            path="/gitlab",
            methods=[apigateway.HttpMethod.POST],
            integration=gitlab_api_integration
        )

        for route in post_gitlab_routes:
            CfnOutput(self, "Gitlab_Systemhook_API", value='Endpoint URL: {}{}'.format(
                self.http_api.url,
                route.path))

    def set_ssm_permission_gitlab(self,
                                  function: lambda_.Function):
        # Grant read access to the gitlab parameters
        parameter_1 = ssm.StringParameter.from_string_parameter_name(
            self, "gitlab-url", "/gitlab/url"
        )
        parameter_2 = ssm.StringParameter.from_secure_string_parameter_attributes(
            self, "gitlab-token",
            parameter_name="/gitlab/token"
        )
        parameter_1.grant_read(function)
        parameter_2.grant_read(function)

