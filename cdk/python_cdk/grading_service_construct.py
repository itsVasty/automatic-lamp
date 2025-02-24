import os

from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigateway,
    aws_apigatewayv2_integrations as integrations,
    aws_lambda_python_alpha as _python_lambda,
    Duration,
    CfnOutput, RemovalPolicy, Stack, Tags
)
from constructs import Construct

from python_cdk.string_utils import src_asset_excludes


class GradingServiceConstruct(Construct):
    """
    This creates the stack for the various graders, queues etc
    """

    def __init__(self, scope: Construct, construct_id: str, events_topic: sns.Topic, events_table: dynamodb.Table,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.lms_functions = []

        self.python_grader_queue = self._create_grader_queue('lms-grading-python')
        self.jupyter_grader_queue = self._create_grader_queue('lms-grading-jupyter')
        self.flutter_grader_queue = self._create_grader_queue('lms-grading-flutter')
        self._create_solutions_bucket()
        self._build_http_grading_handler(events_topic, events_table)
        self._build_sns_grading_handler(events_topic, events_table)

    def _create_solutions_bucket(self):
        """
        Creates an S3 bucket where the solutions source and grading scripts are stored, per activity_id
        """
        region = Stack.of(self).region
        self.solutions_bucket = s3.Bucket(self, f'{region.lower()}-lms-solutions-source')

    def _create_grader_queue(self, queue_id: str):
        dead_letter_queue = sqs.Queue(
            self, f"{queue_id}-dlq",
            queue_name=f"{queue_id}-dlq",
            retention_period=Duration.seconds(1209600)
        )
        grader_queue = sqs.Queue(
            self, f"{queue_id}-queue",
            queue_name=f"{queue_id}-queue",
            visibility_timeout=Duration.seconds(910),
            retention_period=Duration.seconds(14400),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=2,  # Adjust max receive count as needed
                queue=dead_letter_queue
            )
        )
        return grader_queue

    def _build_http_grading_handler(self, events_topic: sns.Topic, events_table: dynamodb.Table):
        # Grading Http Request function - triggered via http
        # TODO: see if we cannot perhaps pacakge the lms-shared package in a Lambda Layer for reuse
        self.grading_http_function = _python_lambda.PythonFunction(
            self, "lms-grading-http-handler",
            function_name="lms-grading-http-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handler",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_grading/handlers/grading_router_http_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "PYTHON_GRADING_QUEUE_NAME": self.python_grader_queue.queue_name,
                "JUPYTER_GRADING_QUEUE_NAME": self.jupyter_grader_queue.queue_name,
                "FLUTTER_GRADING_QUEUE_NAME": self.flutter_grader_queue.queue_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-grading-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
            # TODO We want to keep the previous 2 versions of the function - below not quite working
            # current_version_options=lambda_.VersionOptions(
            #     removal_policy=RemovalPolicy.RETAIN,
            #     retain_only_latest_version=False,
            #     retain_only_latest_n_versions=2,
            # )
        )
        Tags.of(self.grading_http_function).add("service", "lms-grading-service")
        self.lms_functions.append(self.grading_http_function)
        # IAM permissions for SQS for router
        self.python_grader_queue.grant_send_messages(self.grading_http_function)
        # Create HTTP API for grading requests
        self.http_api = apigateway.HttpApi(self, "lms-grading-api")
        # Define the API Gateway integration with the 'router_function' Lambda
        router_integration = integrations.HttpLambdaIntegration(
            'lms-grading-http-integration',
            handler=self.grading_http_function
        )
        # Define the API Gateway route and associate it with the integration
        # TODO define apiKey for security
        grading_routes = self.http_api.add_routes(
            path="/grade",
            methods=[apigateway.HttpMethod.POST],
            integration=router_integration
        )

        for route in grading_routes:
            CfnOutput(self, "Grading API", value='Endpoint URL: {}{}'.format(
                self.http_api.url,
                route.path))

    def _build_sns_grading_handler(self, events_topic: sns.Topic, events_table: dynamodb.Table):
        # Grading Router function - triggered via sns topic
        # TODO: see if we cannot perhaps pacakge the lms-shared package in a Lambda Layer for reuse
        self.router_sns_function = _python_lambda.PythonFunction(
            self, "lms-grading-sns-handler",
            function_name="lms-grading-sns-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handler",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_grading/handlers/grading_router_sns_handler.py",
            timeout=Duration.seconds(360),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "PYTHON_GRADING_QUEUE_NAME": self.python_grader_queue.queue_name,
                "JUPYTER_GRADING_QUEUE_NAME": self.jupyter_grader_queue.queue_name,
                "FLUTTER_GRADING_QUEUE_NAME": self.flutter_grader_queue.queue_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-grading-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(self.router_sns_function).add("service", "lms-grading-service")
        self.lms_functions.append(self.router_sns_function)
        # IAM permissions for SQS for router
        self.python_grader_queue.grant_send_messages(self.router_sns_function)
        self.jupyter_grader_queue.grant_send_messages(self.router_sns_function)
        self.flutter_grader_queue.grant_send_messages(self.router_sns_function)

        # IAM permissions for SNS for router
        events_topic.grant_subscribe(self.router_sns_function)

        # Add event trigger from SQS to function
        subscription = subscriptions.LambdaSubscription(self.router_sns_function,
                                                        filter_policy={
                                                            "event_type": sns.SubscriptionFilter.string_filter(
                                                                allowlist=["grading_request"]
                                                            )
                                                        })
        events_topic.add_subscription(subscription)
