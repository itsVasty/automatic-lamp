import os

from aws_cdk import (
    aws_sns as sns,
    aws_sqs as sqs,
    aws_ssm as ssm,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_apigateway as apigatewayv1,
    aws_apigatewayv2 as apigatewayv2,
    aws_apigatewayv2_integrations as integrations,
    aws_lambda_python_alpha as _python_lambda,
    aws_lambda_event_sources as event_sources,
    Duration,
    CfnOutput, RemovalPolicy, Stack, Tags
)
from aws_cdk.aws_apigatewayv2_authorizers import HttpLambdaAuthorizer
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


class StudentsServiceConstruct(Construct):

    def __init__(self, scope: Construct, construct_id: str, events_topic: sns.Topic, events_table: dynamodb.Table,
                 send_email_queue: sqs.Queue,
                 send_matrix_queue: sqs.Queue,
                 progress_api: apigatewayv1.RestApi,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.lms_functions = []

        self.progress_api = progress_api

        self._build_ddb_tables()
        self._build_content_auth_constructs(events_table, events_topic)

        #these are used by student dashboard
        self._build_student_api(events_table, events_topic)
        self._build_student_progress_constructs(events_table, events_topic)
        self._build_student_curriculum_constructs(events_table, events_topic)

        # these are use for the progress publish service
        self._build_progress_publish_constructs(events_table, events_topic)
        self._build_student_report_handler(events_table, events_topic, send_email_queue, send_matrix_queue)

    def _build_ddb_tables(self):
        """
        Creates the DynamoDB tables used by the student service. This includes
        * student-blocklist: list of blocked students (i.e. students who may not access content or get graded)
        """
        self.blocklist_table = dynamodb.Table(
            self, "lms-student-blocklist",
            table_name='lms-student-blocklist',
            partition_key=dynamodb.Attribute(
                name="student_id",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN
        )

        CfnOutput(
            self, "StudentBlocklistTableName",
            value=self.blocklist_table.table_name,
            description="DynamoDB Student Blocklist table name",
            export_name="StudentBlocklistTableName"
        )

    def _build_content_auth_constructs(self, events_table, events_topic):
        # Function to authorize content requests from Traefik
        content_authorizer_handler = _python_lambda.PythonFunction(
            self, "lms-content-authorizer",
            function_name="lms-content-authorizer",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handle",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/content_authorizer_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "BLOCKLIST_TABLE": self.blocklist_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(content_authorizer_handler).add("service", "lms-student-service")
        self.lms_functions.append(content_authorizer_handler)
        # IAM permissions for SNS for router
        self.blocklist_table.grant_read_write_data(content_authorizer_handler)
        events_topic.grant_publish(content_authorizer_handler)
        # Create HTTP API for grading requests
        http_api = apigatewayv2.HttpApi(self, "content-authorizer-api")
        # Define the API Gateway integration with the 'router_function' Lambda
        content_auth_api_integration = integrations.HttpLambdaIntegration(
            'content-auth-http-integration',
            handler=content_authorizer_handler
        )
        # Define the API Gateway route and associate it with the integration
        content_auth_routes = http_api.add_routes(
            path="/auth",
            methods=[apigatewayv2.HttpMethod.GET, apigatewayv2.HttpMethod.POST],
            integration=content_auth_api_integration
        )
        output_done = False
        for route in content_auth_routes:
            if not output_done:
                CfnOutput(self, 'Content_Auth_API_url', value='Endpoint URL: {}{}'.format(
                    http_api.url,
                    route.path))
                output_done = True

    def _create_publish_queue(self):
        # Create Python grading request SQS with DLQ
        dead_letter_queue = sqs.Queue(
            self, "lms-progress-publish-dlq",
            queue_name="lms-progress-publish-dlq",
            retention_period=Duration.seconds(1209600)
        )
        self.progress_publish_queue = sqs.Queue(
            self, "lms-progress-publish-queue",
            queue_name="lms-progress-publish-queue",
            visibility_timeout=Duration.seconds(2700),
            retention_period=Duration.seconds(14400),
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=2,  # Adjust max receive count as needed
                queue=dead_letter_queue
            )
        )

    def _build_progress_publish_constructs(self, events_table, events_topic):
        # Build Publish SQS queue
        self._create_publish_queue()

        progress_publish_handler = _python_lambda.PythonFunction(
            self, "lms-progress-publish-handler",
            function_name="lms-progress-publish-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="get",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/cohort_publish_http_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "PUBLISH_QUEUE_NAME": self.progress_publish_queue.queue_name,
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(progress_publish_handler).add("service", "lms-student-service")
        self.lms_functions.append(progress_publish_handler)
        # IAM permission to publish to SQS
        self.progress_publish_queue.grant_send_messages(progress_publish_handler)
        # IAM permissions for SNS for router
        events_topic.grant_publish(progress_publish_handler)
        # IAM permissions to read from events-log DDB
        events_table.grant_read_data(progress_publish_handler)

        lambda_integration = apigatewayv1.LambdaIntegration(progress_publish_handler)

        progress_path = self.progress_api.root.add_resource("publish")
        cohort_publish_resource = progress_path.add_resource("{cohort_id}")
        get_progress_method = cohort_publish_resource.add_method(
            "POST",
            lambda_integration,
            api_key_required=True
        )

        CfnOutput(self, "Cohort-Publish-Api-Url", value=f'{self.progress_api.url}{cohort_publish_resource.path}')

        # Build Publish SQS handler
        publish_queue_handler = _python_lambda.PythonFunction(
            self, "lms-publish-sqs-handler",
            function_name="lms-publish-sqs-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handler",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/publish_queue_handler.py",
            timeout=Duration.seconds(900),
            memory_size=3008, #this sets it to use more memory and also 2 vCPUs
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(publish_queue_handler).add("service", "lms-student-service")
        self.lms_functions.append(publish_queue_handler)
        # IAM permission to publish to SQS
        self.progress_publish_queue.grant_consume_messages(publish_queue_handler)
        # IAM permissions for SNS for router
        events_topic.grant_publish(publish_queue_handler)
        # IAM permissions to read from events-log DDB
        events_table.grant_read_data(publish_queue_handler)
        # trigger handler from queue
        publish_queue_handler.add_event_source(
            event_sources.SqsEventSource(
                self.progress_publish_queue,
                batch_size=1,  # Adjust batch size as needed
                max_concurrency=2
            )
        )

        # Grant read access to the google parameters
        google_key_param = ssm.StringParameter.from_secure_string_parameter_attributes(
            self, "google-service_key",
            parameter_name="/google/service_key"
        )
        google_key_param.grant_read(publish_queue_handler)
        self.grant_ssm_read_access(publish_queue_handler, "/google/default_sheet_url/*")

        # Scheduled publish handler
        scheduled_handler = _python_lambda.PythonFunction(
            self, "lms-publish-cron-handler",
            function_name="lms-publish-cron-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handler",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/scheduled_publish_handler.py",
            timeout=Duration.seconds(900),
            environment={  # Optional environment variables for the Lambda function
                "PUBLISH_QUEUE_NAME": self.progress_publish_queue.queue_name,
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(scheduled_handler).add("service", "lms-student-service")
        self.lms_functions.append(scheduled_handler)
        # IAM permission to publish to SQS
        self.progress_publish_queue.grant_send_messages(scheduled_handler)

        # Create the scheduled EventBridge rule
        rule_jan_to_dec = events.Rule(
            self, "HourlyScheduleRuleJanToDec",
            schedule=events.Schedule.cron(
                minute="0",
                hour="6-20",
                week_day="MON-FRI",
                month="*",
                year="*"
            )
        )
        rule_jan_to_dec.add_target(targets.LambdaFunction(scheduled_handler))

    def grant_ssm_read_access(self, function, path):
        function.add_to_role_policy(iam.PolicyStatement(
            actions=["ssm:GetParametersByPath", "ssm:GetParameters", "ssm:GetParameter"],
            resources=[f"arn:aws:ssm:{Stack.of(self).region}:{Stack.of(self).account}:parameter{path}"]
        ))

    def _build_student_report_handler(self, events_table, events_topic, send_email_queue: sqs.Queue,
                 send_matrix_queue: sqs.Queue):
        scheduled_handler = _python_lambda.PythonFunction(
            self, "lms-stdreport-cron-handler",
            function_name="lms-stdreport-cron-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handler",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/scheduled_student_report_handler.py",
            timeout=Duration.seconds(900),
            memory_size=3008, #this sets it to use more memory and also 2 vCPUs
            environment={  # Optional environment variables for the Lambda function
                "SEND_EMAIL_QUEUE_NAME": send_email_queue.queue_name,
                "SEND_MATRIX_QUEUE_NAME": send_matrix_queue.queue_name,
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(scheduled_handler).add("service", "lms-student-service")
        self.lms_functions.append(scheduled_handler)
        send_email_queue.grant_send_messages(scheduled_handler)
        send_matrix_queue.grant_send_messages(scheduled_handler)
        # IAM permissions to read from events-log DDB
        events_table.grant_read_data(scheduled_handler)

        rule_jan_to_dec = events.Rule(
            self, "BiweeklyScheduleRuleJanToDec",
            schedule=events.Schedule.cron(
                minute="0",
                hour="4",
                week_day="MON,WED",
                month="*",
                year="*"
            )
        )
        rule_jan_to_dec.add_target(targets.LambdaFunction(scheduled_handler))

    def _build_student_api(self, events_table, events_topic):
        # create cors options
        cors_options = apigatewayv2.CorsPreflightOptions(
            allow_methods=[apigatewayv2.CorsHttpMethod.GET, apigatewayv2.CorsHttpMethod.POST,
                           apigatewayv2.CorsHttpMethod.PUT, apigatewayv2.CorsHttpMethod.OPTIONS],
            allow_origins=['*'],  # Or specify allowed origins
            allow_headers=['Content-Type', 'X-Amz-Date', 'Authorization', 'X-Api-Key', 'Origin', 'Accept',
                           'Access-Control-Allow-Headers', 'Access-Control-Allow-Methods',
                           'Access-Control-Allow-Origin'],
            max_age=Duration.days(10)
        )
        # Create HTTP API for student requests
        self.student_api = apigatewayv2.HttpApi(self, "student-api",
                                                cors_preflight=cors_options)

        # Define default CORS handler
        handler = _python_lambda.PythonFunction(
            self, "lms-student-options-handler",
            function_name="lms-student-options-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="lambda_handler",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_shared/aws/options_cors_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(handler).add("service", "lms-student-service")
        self.lms_functions.append(handler)

        # define reusable integration
        self.cors_integration = integrations.HttpLambdaIntegration(
            'cors-integration',
            handler=handler
        )

        # define the custom lambda authorizer handler
        authorizer_handler = _python_lambda.PythonFunction(
            self, "lms-student-auth-handler",
            function_name="lms-student-auth-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="handle",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/student_authorizer_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(authorizer_handler).add("service", "lms-student-service")
        self.lms_functions.append(authorizer_handler)

        self._grant_google_id_permission(authorizer_handler)

        # Define the custom auth handler
        self.authorizer = HttpLambdaAuthorizer(
            'lms-student-api-authorizer',
            authorizer_handler,
            authorizer_name='lms-student-api-authorizer',
            identity_source=['$request.header.Authorization']
        )

    def _grant_google_id_permission(self, handler):
        # Grant read access to the google parameters
        if (not hasattr(self, 'google_clientid_param')):
            self.google_clientid_param = ssm.StringParameter.from_string_parameter_name(
                self, "google-clientid", "/google/client_id"
            )
        self.google_clientid_param.grant_read(handler)

    def _build_student_progress_constructs(self, events_table, events_topic):
        student_progress_handler = _python_lambda.PythonFunction(
            self, "lms-student-progress-handler",
            function_name="lms-student-progress-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="get",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/student_progress_http_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(student_progress_handler).add("service", "lms-student-service")
        self.lms_functions.append(student_progress_handler)
        # IAM permissions for SNS for router
        events_topic.grant_publish(student_progress_handler)
        # IAM permissions to read from events-log DDB
        events_table.grant_read_data(student_progress_handler)

        self._grant_google_id_permission(student_progress_handler)

        # Define the API Gateway integration with the 'router_function' Lambda
        student_progress_api_integration = integrations.HttpLambdaIntegration(
            'student-progress-http-integration',
            handler=student_progress_handler
        )

        # Define the API Gateway route and associate it with the integration
        routes = self.student_api.add_routes(
            path="/progress",
            methods=[apigatewayv2.HttpMethod.GET],
            integration=student_progress_api_integration,
            authorizer=self.authorizer
        )

        # Hook op OPTIONS handler for CORS
        self.student_api.add_routes(
            path="/progress",
            methods=[apigatewayv2.HttpMethod.OPTIONS],
            integration=self.cors_integration
        )

        output_done = False
        for route in routes:
            if not output_done:
                CfnOutput(self, 'Student_Progress_API_url', value='Endpoint URL: {}{}'.format(
                    self.student_api.url,
                    route.path))
                output_done = True

    def _build_student_curriculum_constructs(self, events_table, events_topic):
        handler = _python_lambda.PythonFunction(
            self, "lms-student-curriculum-handler",
            function_name="lms-student-curriculum-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="get",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/student_curriculum_http_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-student-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(handler).add("service", "lms-student-service")
        self.lms_functions.append(handler)
        # IAM permissions for SNS for router
        events_topic.grant_publish(handler)
        # IAM permissions to read from events-log DDB
        events_table.grant_read_data(handler)

        self._grant_google_id_permission(handler)

        # Define the API Gateway integration with the 'router_function' Lambda
        student_progress_api_integration = integrations.HttpLambdaIntegration(
            'student-curriculum-http-integration',
            handler=handler
        )

        # Define the API Gateway route and associate it with the integration
        routes = self.student_api.add_routes(
            path="/curriculum",
            methods=[apigatewayv2.HttpMethod.GET],
            integration=student_progress_api_integration,
            authorizer=self.authorizer
        )

        # Hook op OPTIONS handler for CORS
        self.student_api.add_routes(
            path="/curriculum",
            methods=[apigatewayv2.HttpMethod.OPTIONS],
            integration=self.cors_integration
        )

        output_done = False
        for route in routes:
            if not output_done:
                CfnOutput(self, 'Student_Curriculum_API_url', value='Endpoint URL: {}{}'.format(
                    self.student_api.url,
                    route.path))
                output_done = True
