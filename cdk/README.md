# LMS CDK

This is an [AWS CDK](https://docs.aws.amazon.com/cdk/v2/guide/getting_started.html) project, using Python, to deploy the LMS to AWS. 

The `cdk.json` file tells the CDK Toolkit how to CDK app.

This project is set up like a standard Python project.  The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.

## Environment Setup

**First change to the `cdk` dir in terminal**

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

## Deployment Architecture

The LMS CDK project defines a comprehensive AWS infrastructure for the Learning Management System. The main stack, `LMSFullStack`, is composed of several services, each implemented as a separate construct:

1. **Event Service**: Handles event management and logging using SNS topics and DynamoDB tables.
2. **GitLab Connect Service**: Integrates with GitLab for project submissions and management.
3. **Grading Service**: Manages the grading process, including queues for different types of assignments (Python, Jupyter, Flutter).
4. **Student Notifiers Service**: Handles notifications to students through various channels (email, Matrix).
5. **Students Service**: Manages student-related operations, including progress tracking, curriculum access, and content authorization.

Key components of the architecture include:

- Lambda functions for serverless compute
- DynamoDB tables for data storage
- SNS topics and SQS queues for messaging and event handling
- API Gateway for RESTful and HTTP APIs
- IAM roles and policies for security
- CloudWatch for logging and monitoring

The architecture is designed to be scalable, serverless, and event-driven, allowing for efficient handling of LMS operations such as grading, student progress tracking, and notifications.

## Deploy and run local

**First start Docker**

If you have not done so before, bootstrap the local CDK environment:

```
cdklocal bootstrap
```

At this point you can now synthesize the CloudFormation template for this code.

```
$ cdklocal synth
```

Now start [LocalStack](https://github.com/localstack/localstack)

```
localstack start -d
```

Make sure the [CDK wrapper for Localstack](https://github.com/localstack/aws-cdk-local?tab=readme-ov-file) is installed:

```
npm install -g aws-cdk-local aws-cdk
```

Now deploy the LMS to the local stack:

```
cdklocal deploy
```

Install [awslocal](https://github.com/localstack/awscli-local) to be able to interrogate and invoke your local resources.

And now you can example check what Lambda functions are deployed:

```
awslocal lambda list-functions 
```

You can also invoke specific functions, e.g. :

```
awslocal lambda invoke \
    --function-name my-function \
    --cli-binary-format raw-in-base64-out \
    --payload '{ "name": "Bob" }' \
    response.json
```

_Note: you can also use the [LocalStack UI](https://app.localstack.cloud/inst/default/resources/cloudformation/stacks) to visually browse your LocalStack status and resources._

### Stopping LocalStack

To stop your localstack environment: `localstack stop`

## Deploy to AWS

**First start Docker**

At this point you can now synthesize the CloudFormation template for this code.

```
$ DEPLOY_STAGE=DEV cdk synth --profile <your-wtc-profile>
```

To add additional dependencies, for example other CDK libraries, just add
them to your `setup.py` file and rerun the `pip install -r requirements.txt`
command.

To actually deploy, run:

```
$ DEPLOY_STAGE=DEV cdk deploy --profile <your-wtc-profile>
```


## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!

## To Test

- ensure you are in `cdk` dir
- run `pytest tests/`

## References

- Python CDK examples: https://github.com/aws-samples/aws-cdk-examples/tree/main/python
- Python CDK workshop: https://cdkworkshop.com/30-python/20-create-project/300-structure.html

## TODOs

- [] when running in LocalStack, use mocked grader instead of ECR-deployed grader (ECR only supported by Pro Localstack)


## Setting up deployment for new AWS account

The deployment infrastructure is meant for seperate instances of the system to deploy to seperate AWS accounts. 

To setup a new AWS account for deployment, follow these steps.

### Manual AWS Steps

1. Create the AWS account (best is to use Control Tower and create an account under the organisation)
2. Using IAM Identity Center, assign permissions to the relevant users or groups to this account. 
3. Log in with user with IAM permissions to the account
4. Copy the **AWS account id** (a long numeric id). 
5. Create an IAM user with security credentials (i.e. Access Key and Secret) with the necessary permissions to create new AWS resources and set permissions on those.
6. Store the secret and key under the relevant Github secrets for use by the Github workflow action that must deploy the system. 
7. Now navigate to AWS Apigateway service, and create an api key calles `progress-api-key`
8. After the api key is created, copy the `id` value in the Api Key Details section.
9. Create a AWS Systems Manager Parameter Store entry `gitlab/url` and store the url to the gitlab instance where the students submit projects
10. Create a AWS Systems Manager Parameter Store **secure** entry `gitlab/token` and store a PAT to the gitlab instance where the students submit projects

### CDK Deploy steps.

0. First run `cdk bootstrap` on the new account (using the AWS IAM credentials from previous)
1. Edit the `app.py` file, and add a value for `DEPLOY_STAGE` that represent this account deploy, mapped to the **AWS account id** copied earlier.
2. Edit `students_service_construct.py` and add a mapping from the new `DEPLOY_STAGE` to the **Api Key id** copied earlier.

### Github Steps

1. Set the IAM Access Key and Secret as Github Secrets (for use by Actions) - the name of the vars must match what is expected in the github action that will do the deployment.
2. Copy the `./github/workflows/deploy-to-aws-prod.yml` template and adjust to use the Github secrets defined in previous step.

Now you should be ready to deploy.

### After deploy steps

1. Ensure relevant grading source files are added to the S3 Solutions bucket.
2. Import or edit the relevant curriculum and cohort schedules.
3. Setup any custom domain mappings you need to point to the various API Gateway endpoints.