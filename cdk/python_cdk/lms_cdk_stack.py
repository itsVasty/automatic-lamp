import os

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_lambda_python_alpha as _python_lambda,
)
from constructs import Construct
from datadog_cdk_constructs_v2 import Datadog, DatadogLambda

from python_cdk.cohort_service_construct import CohortServiceConstruct
from python_cdk.events_service_construct import EventsServiceConstruct
from python_cdk.gitlab_connect_construct import GitlabConnectConstruct
from python_cdk.grading_service_construct import GradingServiceConstruct
from python_cdk.students_service_construct import StudentsServiceConstruct
from python_cdk.student_notifiers_construct import StudentNotifiersConstruct

class LMSFullStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # self._build_python_lambda_layer()
        self.event_service = self._build_event_service()
        self.notifier_service = self._build_student_notifiers()
        self.event_service.set_notification_configuration(self.notifier_service.send_email_queue,
                                                          self.notifier_service.send_matrix_queue)
        self.grading_service = self._build_grading_service()
        self.gitlab_connect_service = self._build_gitlab_connect_service()
        self.cohort_service = self._build_cohort_service()
        self.students_service = self._build_students_service()
        self._build_datadog_service()

    # def _build_python_lambda_layer(self):
    #     layer_code = lambda_.Code.from_asset(
    #         "../source",
    #         exclude=[".venv/**"]
    #     )
    #     self.python_layer = lambda_.LayerVersion(
    #         self,
    #         "lms-python-layer",
    #         code=layer_code,
    #         compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
    #     )

    def _build_event_service(self) -> EventsServiceConstruct:
        return EventsServiceConstruct(self, 'LmsEventService')

    def _build_gitlab_connect_service(self) -> GitlabConnectConstruct:
        return GitlabConnectConstruct(self, 'LmsGitlabConnectService', self.event_service.events_topic, self.event_service.events_table,
                                      self.notifier_service.send_email_queue, self.notifier_service.send_matrix_queue,)

    def _build_students_service(self) -> StudentsServiceConstruct:
        return StudentsServiceConstruct(self, 'LmsStudentsService', self.event_service.events_topic,
                                        self.event_service.events_table,
                                        self.notifier_service.send_email_queue, self.notifier_service.send_matrix_queue,
                                        self.cohort_service.progress_api)

    def _build_cohort_service(self) -> CohortServiceConstruct:
        return CohortServiceConstruct(self, 'LmsCohortService', self.event_service.events_topic,
                                        self.event_service.events_table, )

    def _build_grading_service(self) -> GradingServiceConstruct:
        return GradingServiceConstruct(self, 'LmsGradingService', self.event_service.events_topic, self.event_service.events_table)

    def _build_student_notifiers(self) -> StudentNotifiersConstruct:
        return StudentNotifiersConstruct(self, 'LmsStudentNotifiers', self.event_service.events_topic, self.event_service.events_table)

    def _build_datadog_service(self) -> None:
        dd_api_key = os.getenv('DATADOG_API_KEY')
        datadog = Datadog(self,
                  "lms-datadog-lambda",
                    python_layer_version=104,
                    extension_layer_version=68,
                    create_forwarder_permissions=True,
                      capture_lambda_payload=False,
                      flush_metrics_to_logs=True,
                      enable_datadog_tracing=True,
                      enable_merge_xray_traces=False,
                      enable_datadog_logs=True,
                      inject_log_context=True,
                      log_level="debug" if os.getenv('DEPLOY_STAGE', 'DEV') == 'DEV' else 'info',
                      site="datadoghq.eu",
                      api_key=dd_api_key,
                      env=os.getenv('DEPLOY_STAGE', 'DEV'),
                      service=f"LMS-{os.getenv('DEPLOY_STAGE', 'DEV')}",
                      version="1.0.0",
                      tags="lms,lambda,python,datadog,aws")

        lms_functions = []
        lms_functions.extend(self.cohort_service.lms_functions)
        lms_functions.extend(self.event_service.lms_functions)
        lms_functions.extend(self.gitlab_connect_service.lms_functions)
        lms_functions.extend(self.grading_service.lms_functions)
        lms_functions.extend(self.notifier_service.lms_functions)
        lms_functions.extend(self.students_service.lms_functions)
        datadog.add_lambda_functions(
            lambda_functions=lms_functions,
        )
