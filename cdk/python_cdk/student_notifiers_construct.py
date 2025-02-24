import os

from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_ssm as ssm,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_ses as ses,
    aws_sns_subscriptions as subscriptions,
    aws_lambda as lambda_,
    aws_lambda_event_sources as event_sources,
    aws_lambda_python_alpha as _python_lambda,
    Duration, RemovalPolicy, CfnOutput, Tags,
)
from constructs import Construct

from python_cdk.string_utils import src_asset_excludes


class StudentNotifiersConstruct(Construct):
    """
    This creates the stack for the various notifiers (right now just reviews)
    """

    def __init__(self, scope: Construct, construct_id: str, events_topic: sns.Topic, events_table: dynamodb.Table,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.lms_functions = []

        self.parameter_1 = None
        self.parameter_2 = None
        self.parameter_3 = None

        self._build_ddb_tables()
        self._build_sns_matrix_notifier(events_topic, events_table)
        self._build_sns_email_notifier(events_topic, events_table)

        self.send_email_queue = self._create_send_queue('lms-notify-email')
        self.send_matrix_queue = self._create_send_queue('lms-notify-matrix')
        self.send_email_function = self._build_sqs_send_handler(
            'lms-notifier-email',
            'send_email_sqs_handler.py',
            self.send_email_queue, events_topic, events_table)
        self.send_matrix_function = self._build_sqs_send_handler(
            'lms-notifier-matrix',
            'send_matrix_sqs_handler.py',
            self.send_matrix_queue, events_topic, events_table)
        self.set_ssm_permission_matrix(self.send_matrix_function)
        self.matrix_table.grant_read_write_data(self.send_matrix_function)
        self._apply_email_permissions()

    def _create_send_queue(self, queue_id: str):
        dead_letter_queue = sqs.Queue(
            self, f"{queue_id}-dlq",
            queue_name=f"{queue_id}-dlq",
            retention_period=Duration.seconds(1209600)
        )
        send_queue = sqs.Queue(
            self, f"{queue_id}-queue",
            queue_name=f"{queue_id}-queue",
            visibility_timeout=Duration.seconds(910),
            retention_period=Duration.seconds(14400),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=2,  # Adjust max receive count as needed
                queue=dead_letter_queue
            )
        )
        return send_queue


    def _build_ddb_tables(self):
        self.matrix_table = dynamodb.Table(
            self, "lms-matrix-rooms",
            table_name='lms-matrix-rooms',
            partition_key=dynamodb.Attribute(
                name="student_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expire_at",
            removal_policy=RemovalPolicy.RETAIN
        )

        CfnOutput(
            self, "MatrixTableName",
            value=self.matrix_table.table_name,
            description="DynamoDB Matrix table name",
            export_name="MatrixTableName"
        )

    def _build_sns_matrix_notifier(self, events_topic: sns.Topic, events_table: dynamodb.Table):
        self.matrix_sns_function = _python_lambda.PythonFunction(
            self, "lms-review-matrix-handler",
            function_name="lms-review-matrix-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handler",  # Name of the Lambda handler function
            # Runtime environment for the Lambda function
            runtime=lambda_.Runtime.PYTHON_3_11,
            index="lms_notifiers/handlers/review_matrix_handler.py",
            # Optional timeout for the Lambda function
            timeout=Duration.seconds(900),
            memory_size=1024, #this sets it to use more memory and also 2 vCPUs
            environment={  # Optional environment variables for the Lambda function
                "MATRIX_TABLE": self.matrix_table.table_name,
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-notifiers",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            ),
            reserved_concurrent_executions=1,
        )
        Tags.of(self.matrix_sns_function).add("service", "lms-student-notifiers")
        self.lms_functions.append(self.matrix_sns_function)
        self.set_ssm_permission_matrix(self.matrix_sns_function)
        events_topic.grant_subscribe(self.matrix_sns_function)
        self.matrix_table.grant_read_write_data(self.matrix_sns_function)

        # Add event trigger from SNS to function
        subscription = subscriptions.LambdaSubscription(self.matrix_sns_function,
                                                        filter_policy={
                                                            "event_type": sns.SubscriptionFilter.string_filter(
                                                                allowlist=[
                                                                    "review"]
                                                            )
                                                        })
        events_topic.add_subscription(subscription)

    def _build_sns_email_notifier(self, events_topic: sns.Topic, events_table: dynamodb.Table):
        self.email_sns_function = _python_lambda.PythonFunction(
            self, "lms-review-email-handler",
            function_name="lms-review-email-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handler",  # Name of the Lambda handler function
            # Runtime environment for the Lambda function
            runtime=lambda_.Runtime.PYTHON_3_11,
            index="lms_notifiers/handlers/review_email_handler.py",
            # Optional timeout for the Lambda function
            timeout=Duration.seconds(360),
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-notifiers",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            reserved_concurrent_executions=2,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(self.email_sns_function).add("service", "lms-student-notifiers")
        self.lms_functions.append(self.email_sns_function)
        # IAM permissions for SNS for router
        events_topic.grant_subscribe(self.email_sns_function)

        # Add event trigger from SNS to function
        subscription = subscriptions.LambdaSubscription(self.email_sns_function,
                                                        filter_policy={
                                                            "event_type": sns.SubscriptionFilter.string_filter(
                                                                allowlist=[
                                                                    "review"]
                                                            )
                                                        })
        events_topic.add_subscription(subscription)


    def _apply_email_permissions(self):
        # IAM permissions to send email
        email_identity = ses.EmailIdentity.from_email_identity_name(
            self, "lms-email-identity",
            email_identity_name="lms-dev.wethinkco.de" if os.getenv('DEPLOY_STAGE',
                                                                    'LOCAL') == "DEV" else "lms.wethinkco.de"
        )
        email_identity.grant_send_email(self.email_sns_function)
        email_identity.grant_send_email(self.send_email_function)
        # Add specific emails for DEV
        if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV":
            email_identity = ses.EmailIdentity.from_email_identity_name(
                self, "lms-email-herman",
                email_identity_name="herman@wethinkcode.co.za"
            )
            email_identity.grant_send_email(self.email_sns_function)
            email_identity.grant_send_email(self.send_email_function)
            email_identity = ses.EmailIdentity.from_email_identity_name(
                self, "lms-email-fen",
                email_identity_name="fen@wethinkcode.co.za"
            )
            email_identity.grant_send_email(self.email_sns_function)
            email_identity.grant_send_email(self.send_email_function)

    def set_ssm_permission_matrix(self,
                                  function: lambda_.Function):
        if not self.parameter_1:
            self.parameter_1 = ssm.StringParameter.from_string_parameter_name(
                self, "matrix-url", "/matrix/url"
            )
            self.parameter_2 = ssm.StringParameter.from_string_parameter_name(
                self, "matrix-username", "/matrix/username"
            )
            self.parameter_3 = ssm.StringParameter.from_secure_string_parameter_attributes(
                self, "matrix-password",
                parameter_name="/matrix/password"
            )

        self.parameter_1.grant_read(function)
        self.parameter_2.grant_read(function)
        self.parameter_3.grant_read(function)

    def _build_sqs_send_handler(self, handler_name: str, python_file: str, queue: sqs.Queue, events_topic: sns.Topic, events_table: dynamodb.Table):
        queue_handler = _python_lambda.PythonFunction(
            self, handler_name,
            function_name=handler_name,
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handler",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_notifiers/handlers/"+python_file,
            timeout=Duration.seconds(900),
            environment={  # Optional environment variables for the Lambda function
                "MATRIX_TABLE": self.matrix_table.table_name,
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-notifier-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(queue_handler).add("service", "lms-student-notifiers")
        self.lms_functions.append(queue_handler)
        # IAM permission to publish to SQS
        queue.grant_consume_messages(queue_handler)
        # trigger handler from queue
        queue_handler.add_event_source(
            event_sources.SqsEventSource(
                queue,
                batch_size=1,  # Adjust batch size as needed
                max_concurrency=2
            )
        )
        return queue_handler
