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


class CohortServiceConstruct(Construct):

    def __init__(self, scope: Construct, construct_id: str, events_topic: sns.Topic, events_table: dynamodb.Table,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.lms_functions = []

        #these are meant for use by SP team to track progress
        self.progress_api = self._build_cohort_api()
        self._build_cohort_progress_constructs(events_table, events_topic)
        self._build_cohort_summary_constructs(events_table, events_topic)
        self._build_cohort_student_constructs(events_table, events_topic)
        self._build_cohort_curriculum_constructs(events_table, events_topic)
        # self._build_default_options_construct()

    def _build_cohort_api(self) -> apigatewayv1.RestApi:
        # Create HTTP API for grading requests
        progress_api = apigatewayv1.RestApi(self,
                                                 "progress-api",
                                                 default_cors_preflight_options=apigatewayv1.CorsOptions(
                                                     allow_origins=apigatewayv1.Cors.ALL_ORIGINS,
                                                     allow_methods=apigatewayv1.Cors.ALL_METHODS,
                                                     allow_headers=['Content-Type', 'X-Amz-Date', 'Authorization',
                                                                    'X-Api-Key', 'Origin', 'Accept',
                                                                    'Access-Control-Allow-Headers',
                                                                    'Access-Control-Allow-Methods',
                                                                    'Access-Control-Allow-Origin'],
                                                     max_age=Duration.days(10),  # Optional: cache preflight results
                                                     allow_credentials=True
                                                 )
                                                 )
        existing_api_key_id = _get_progress_api_key()
        progress_api_key = apigatewayv1.ApiKey.from_api_key_id(self, "progress-api-key", existing_api_key_id)
        usage_plan = apigatewayv1.UsagePlan(self, "progress-api-usageplan",
                                            api_stages=[
                                                apigatewayv1.UsagePlanPerApiStage(api=progress_api,
                                                                                  stage=progress_api.deployment_stage)
                                            ]
                                            )
        usage_plan.add_api_key(progress_api_key)

        return progress_api

    def _build_default_options_construct(self):
        # Create a default OPTIONS integration that will be used for all resources
        default_options_integration = apigatewayv1.MockIntegration(
            integration_responses=[
                apigatewayv1.IntegrationResponse(
                    status_code="200",
                    response_parameters={
                        'method.response.header.Access-Control-Allow-Headers': "'Content-Type', 'X-Amz-Date', 'Authorization','X-Api-Key', 'Origin', 'Accept','Access-Control-Allow-Headers','Access-Control-Allow-Methods','Access-Control-Allow-Origin'",
                        'method.response.header.Access-Control-Allow-Methods': "'GET,POST,PUT,DELETE,OPTIONS'",
                        'method.response.header.Access-Control-Allow-Origin': "'*'"
                    }
                )
            ],
            passthrough_behavior=apigatewayv1.PassthroughBehavior.WHEN_NO_MATCH,
            request_templates={
                "application/json": '{"statusCode": 200}'
            }
        )

        # Add default method options response
        options_response = apigatewayv1.MethodResponse(
            status_code="200",
            response_parameters={
                'method.response.header.Access-Control-Allow-Headers': True,
                'method.response.header.Access-Control-Allow-Methods': True,
                'method.response.header.Access-Control-Allow-Origin': True
            }
        )

        # Add OPTIONS method to all resources that need it
        resource_paths = {
            self.curriculum_path: 'curriculum',
            self.progress_path: 'progress',
            self.summary_path: 'summary',
            self.student_path: 'student'
        }
        for resource, path_name in resource_paths.items():
            apigatewayv1.Method(
                    self,
                    f'options-{path_name}-method',
                    http_method="OPTIONS",
                    resource=resource,
                    options=apigatewayv1.MethodOptions(
                        method_responses=[options_response]
                    ),
                    integration=default_options_integration
                )

    def _build_cohort_curriculum_constructs(self, events_table, events_topic):
        # Function to authorize content requests from Traefik
        handler = _python_lambda.PythonFunction(
            self, "lms-cohort-curri-http-handler",
            function_name="lms-cohort-curri-http-handler",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="get",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/cohort_curriculum_http_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            memory_size=2048, #this sets it to use more memory and also 2 vCPUs
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-cohort-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(handler).add("service", "lms-cohort-service")
        self.lms_functions.append(handler)
        # IAM permissions for SNS for router
        events_topic.grant_publish(handler)
        # IAM permissions to read from events-log DDB
        events_table.grant_read_data(handler)

        lambda_integration = apigatewayv1.LambdaIntegration(handler)

        self.curriculum_path = self.progress_api.root.add_resource("curriculum")
        cohort_progress_resource = self.curriculum_path.add_resource("{cohort_id}")
        get_progress_method = cohort_progress_resource.add_method(
            "GET",
            lambda_integration,
            api_key_required=True
        )
        # # options_method = cohort_progress_resource.add_method(
        # #     "OPTIONS",
        # #     self.options_integration,
        # #     id = "cohort_curriculum_options"
        # # )
        # options_method = apigatewayv1.Method(
        #     self,
        #     "Cohort-Curriculum-Options-Method",
        #     http_method="OPTIONS",
        #     resource=cohort_progress_resource,
        #     integration=self.options_integration
        # )

        CfnOutput(self, "Cohort-Curriculum-Api-Url", value=f'{self.progress_api.url}{cohort_progress_resource.path}')

    def _build_cohort_progress_constructs(self, events_table, events_topic):
        # Function to authorize content requests from Traefik
        cohort_progress_handler = _python_lambda.PythonFunction(
            self, "lms-cohort-progress-http",
            function_name="lms-cohort-progress-http",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="get",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/cohort_progress_http_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            memory_size=2048, #this sets it to use more memory and also 2 vCPUs
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-cohort-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(cohort_progress_handler).add("service", "lms-cohort-service")
        self.lms_functions.append(cohort_progress_handler)
        # IAM permissions for SNS for router
        events_topic.grant_publish(cohort_progress_handler)
        # IAM permissions to read from events-log DDB
        events_table.grant_read_data(cohort_progress_handler)

        lambda_integration = apigatewayv1.LambdaIntegration(cohort_progress_handler)

        self.progress_path = self.progress_api.root.add_resource("progress")
        cohort_progress_resource = self.progress_path.add_resource("{cohort_id}")
        get_progress_method = cohort_progress_resource.add_method(
            "GET",
            lambda_integration,
            api_key_required=True
        )
        # )

        CfnOutput(self, "Cohort-Progress-Api-Url", value=f'{self.progress_api.url}{cohort_progress_resource.path}')

    def _build_cohort_summary_constructs(self, events_table, events_topic):
        # Function to authorize content requests from Traefik
        cohort_summary_handler = _python_lambda.PythonFunction(
            self, "lms-cohort-summary-htto",
            function_name="lms-cohort-summary-http",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="get",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/cohort_summary_http_handler.py",
            timeout=Duration.seconds(30),
            memory_size=2048, #this sets it to use more memory and also 2 vCPUs
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-cohort-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(cohort_summary_handler).add("service", "lms-cohort-service")
        self.lms_functions.append(cohort_summary_handler)
        # IAM permissions for SNS for router
        events_topic.grant_publish(cohort_summary_handler)
        # IAM permissions to read from events-log DDB
        events_table.grant_read_data(cohort_summary_handler)

        lambda_integration = apigatewayv1.LambdaIntegration(cohort_summary_handler)

        self.summary_path = self.progress_api.root.add_resource("summary")
        cohort_summary_resource = self.summary_path.add_resource("{cohort_id}")
        get_progress_method = cohort_summary_resource.add_method(
            "GET",
            lambda_integration,
            api_key_required=True
        )

        CfnOutput(self, "Cohort-Summary-Api-Url", value=f'{self.progress_api.url}{cohort_summary_resource.path}')

    def _build_cohort_student_constructs(self, events_table, events_topic):
        cohort_student_handler = _python_lambda.PythonFunction(
            self, "lms-cohort-student-http",
            function_name="lms-cohort-student-http",
            entry="../source",  # Path to the Python file containing the Lambda function
            handler="get",  # Name of the Lambda handler function
            runtime=lambda_.Runtime.PYTHON_3_11,  # Runtime environment for the Lambda function
            index="lms_students/handlers/cohort_student_http_handler.py",
            timeout=Duration.seconds(30),  # Optional timeout for the Lambda function
            memory_size=2048, #this sets it to use more memory and also 2 vCPUs
            environment={  # Optional environment variables for the Lambda function
                "EVENTS_TOPIC_ARN": events_topic.topic_arn,
                "EVENTS_TABLE": events_table.table_name,
                "STAGE": os.getenv('DEPLOY_STAGE', 'LOCAL'),
                "POWERTOOLS_SERVICE_NAME": "lms-cohort-service",
                "POWERTOOLS_LOG_LEVEL": "DEBUG" if os.getenv('DEPLOY_STAGE', 'LOCAL') == "DEV" else "INFO"
            },
            tracing=lambda_.Tracing.ACTIVE,
            bundling=_python_lambda.BundlingOptions(
                asset_excludes=src_asset_excludes
            )
        )
        Tags.of(cohort_student_handler).add("service", "lms-cohort-service")
        self.lms_functions.append(cohort_student_handler)
        # IAM permissions for SNS for router
        events_topic.grant_publish(cohort_student_handler)
        # IAM permissions to read from events-log DDB
        events_table.grant_read_data(cohort_student_handler)

        lambda_integration = apigatewayv1.LambdaIntegration(cohort_student_handler)

        self.student_path = self.progress_api.root.add_resource("student")
        cohort_student_resource = self.student_path.add_resource("{student_id}")
        get_progress_method = cohort_student_resource.add_method(
            "GET",
            lambda_integration,
            api_key_required=True
        )

        CfnOutput(self, "Cohort-Student-Api-Url", value=f'{self.progress_api.url}{cohort_student_resource.path}')
