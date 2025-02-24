import os

from aws_cdk import (
    aws_sns as sns,
    aws_sqs as sqs,
    aws_sns_subscriptions as subscriptions,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigatewayv1,
    aws_lambda_python_alpha as _python_lambda,
    Duration,
    CfnOutput, RemovalPolicy, Tags
)
from constructs import Construct

from python_cdk.string_utils import src_asset_excludes

# map DEPLOY_STAGE to progress api key
progress_api_key_map = {
    'LOCAL': 'whatever',
    'DEV': 'g9znes2a87',
    'PROD': 'v4fcxt1bk1'
}


def _get_progress_api_key():
    stage = os.getenv('DEPLOY_STAGE', 'LOCAL')
    return progress_api_key_map[stage]


class EventsServiceConstruct(Construct):
    """
    Creates the infrastructure for the events system, including:
    - SQS for capturing events into the system
    - Handler for processing SNS messages and store to main events log DDB
    - DDB table for persisting events, with a DDBEventsStream
    - DDB Events handler for processing grading request events (although this needs to be in the grading service)
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.lms_functions = []

        self._build_ddb_tables()
        self._build_events_topic_and_handler()
        self._build_events_api()
        self._build_events_http_handlers()

    def _build_events_topic_and_handler(self):
        #TODO: what else do we want to configure in topic? timeouts etc
        self.events_topic = sns.Topic(self, "lms-events-topic",
                                      topic_name="lms-events-topic")

        # Events SNS function - triggered via sqs
        self.events_sns_function = _python_lambda.PythonFunction(
            self, "lms-events-sns-handler",
            function_name="lms-events-sns-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handler",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_events/handlers/events_sns_handler.py",
            timeout=Duration.seconds(360),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "SEND_EMAIL_QUEUE_NAME": 'lms-notify-email-queue',
                "SEND_MATRIX_QUEUE_NAME": 'lms-notify-matrix-queue',
                "EVENTS_TOPIC_ARN": self.events_topic.topic_arn,
                "EVENTS_TABLE": self.events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-events-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(self.events_sns_function).add("service", "lms-events-service")
        self.lms_functions.append(self.events_sns_function)
        # Grant permission to event sqs handler to read and write to the eventslog table
        self.events_table.grant_read_write_data(self.events_sns_function)

        # The events handler must subscribe to and publish to the topic
        self.events_topic.grant_subscribe(self.events_sns_function)
        self.events_topic.grant_publish(self.events_sns_function)

        # Subscribe the Lambda function to the SNS topic without a filter
        subscription = subscriptions.LambdaSubscription(self.events_sns_function)
        self.events_topic.add_subscription(subscription)

    def set_notification_configuration(self,
                 send_email_queue: sqs.Queue,
                 send_matrix_queue: sqs.Queue):
        send_email_queue.grant_send_messages(self.events_sns_function)
        send_matrix_queue.grant_send_messages(self.events_sns_function)

    def _build_ddb_tables(self):
        # Define the table
        self.events_table = dynamodb.Table(
            self, "lms-events-log",
            table_name='lms-events-log',
            partition_key=dynamodb.Attribute(
                name="id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
            time_to_live_attribute="expire_at",
            removal_policy=RemovalPolicy.RETAIN
        )

        # Define global secondary indexes
        self.events_table.add_global_secondary_index(
            index_name="BySourceIdIndex",
            partition_key=dynamodb.Attribute(
                name="source_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        self.events_table.add_global_secondary_index(
            index_name="ByStudentIdIndex",
            partition_key=dynamodb.Attribute(
                name="student_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        self.events_table.add_global_secondary_index(
            index_name="ByCohortIdIndex",
            partition_key=dynamodb.Attribute(
                name="cohort_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        self.events_table.add_global_secondary_index(
            index_name="ByActivityIdIndex",
            partition_key=dynamodb.Attribute(
                name="activity_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        self.events_table.add_global_secondary_index(
            index_name="ByEventTypeIndex",
            partition_key=dynamodb.Attribute(
                name="event_type",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # Output the table name
        CfnOutput(
            self, "EventsTableName",
            value=self.events_table.table_name,
            description="DynamoDB Events table name",
            export_name="EventsTableName"
        )

    def _build_events_api(self):
        # Create HTTP API for grading requests
        self.events_api = apigatewayv1.RestApi(self, "events-api")
        existing_api_key_id = _get_progress_api_key()
        events_api_key = apigatewayv1.ApiKey.from_api_key_id(self, "events-api-key", existing_api_key_id)
        usage_plan = apigatewayv1.UsagePlan(self, "events-api-usageplan",
                                            api_stages=[
                                                apigatewayv1.UsagePlanPerApiStage(api=self.events_api,
                                                                                  stage=self.events_api.deployment_stage)
                                            ]
                                            )
        usage_plan.add_api_key(events_api_key)

    def _build_events_http_handlers(self):
        # GET events handler
        handler = _python_lambda.PythonFunction(
            self, "lms-events-http-handler",
            function_name="lms-events-http-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="get",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_events/handlers/events_http_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            memory_size=2048, #this sets it to use more memory and also 2 vCPUs
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": self.events_topic.topic_arn,
                "EVENTS_TABLE": self.events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-events-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(handler).add("service", "lms-events-service")
        self.lms_functions.append(handler)
        # IAM permissions for SNS for router
        self.events_topic.grant_publish(handler)
        # IAM permissions to read from events-log DDB
        self.events_table.grant_read_data(handler)

        lambda_integration = apigatewayv1.LambdaIntegration(handler)

        events_path = self.events_api.root.add_resource("events")
        events_resource = events_path.add_resource("{event_type}")
        events_get_method = events_resource.add_method(
            "GET",
            lambda_integration,
            api_key_required=True
        )

        CfnOutput(self, "Events-Get-Api-Url", value=f'{self.events_api.url}{events_resource.path}')

        # POST event handler
        handler = _python_lambda.PythonFunction(
            self, "lms-events-post-handler",
            function_name="lms-events-post-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="post",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_events/handlers/events_update_http_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": self.events_topic.topic_arn,
                "EVENTS_TABLE": self.events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-events-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(handler).add("service", "lms-events-service")
        self.lms_functions.append(handler)
        # IAM permissions for SNS for router
        self.events_topic.grant_publish(handler)
        # IAM permissions to read from events-log DDB
        self.events_table.grant_read_data(handler)

        update_lambda_integration = apigatewayv1.LambdaIntegration(handler)

        events_update_method = events_path.add_method(
            "POST",
            update_lambda_integration,
            api_key_required=True
        )

        CfnOutput(self, "Events-Post-Api-Url", value=f'{self.events_api.url}{events_path.path}')

        # POST replay handler
        handler = _python_lambda.PythonFunction(
            self, "lms-events-replay-handler",
            function_name="lms-events-replay-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="post",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_events/handlers/events_replay_http_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            memory_size=2048, #this sets it to use more memory and also 2 vCPUs
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": self.events_topic.topic_arn,
                "EVENTS_TABLE": self.events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-events-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(handler).add("service", "lms-events-service")
        self.lms_functions.append(handler)
        # IAM permissions for SNS for router
        self.events_topic.grant_publish(handler)
        # IAM permissions to read from events-log DDB
        self.events_table.grant_read_data(handler)

        post_lambda_integration = apigatewayv1.LambdaIntegration(handler)

        replay_path = events_path.add_resource('replay')
        events_post_method = replay_path.add_method(
            "POST",
            post_lambda_integration,
            api_key_required=True
        )

        CfnOutput(self, "Events-Replay-Api-Url", value=f'{self.events_api.url}{replay_path.path}')
