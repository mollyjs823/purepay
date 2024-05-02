# PurePay - AWS Lambda Transaction Handler

This repository contains an AWS Lambda function designed to handle transaction processes using AWS services like DynamoDB. It supports operations such as verifying transactions, authenticating merchants, and checking account balances or credit limits within DynamoDB tables.

## Project Overview

The Lambda function is triggered by API requests containing transaction data. It performs validations, checks with DynamoDB for merchant authentication and bank account details, and processes transactions based on account type (credit or debit). It also handles potential bank failures and records transaction statuses.

## Key Features

- **Transaction Validation**: Ensures all required fields are present and correct in the transaction request.
- **Merchant Authentication**: Verifies merchants against stored credentials in DynamoDB.
- **Credit and Balance Verification**: Checks if the account has sufficient funds or credit before approving transactions.
- **Error Handling**: Manages different error states, including insufficient funds, bank failures, and data mismatches.

## Technologies Used

- **AWS Lambda**: Serverless computing to run the code based on request/response triggers.
- **AWS DynamoDB**: NoSQL database to store and retrieve transaction-related data.
- **Python**: Lambda function is written in Python, utilizing libraries such as `boto3` and `json`.

## Setup and Deployment

1. **AWS Management Console**:
   - Create DynamoDB tables: `transactions`, `merchants`, and `banks` with the necessary schema.
   - Deploy the Lambda function by uploading the Python script.

2. **Environment Variables**:
   - Ensure that the Lambda function has access to the AWS resources and permissions to interact with DynamoDB.

3. **API Gateway**:
   - Configure an API Gateway to trigger the Lambda function upon HTTP requests.

## Repository Contents

- `lambda_function.py`: The main Python script for the Lambda function.
- `requirements.txt`: Required libraries for the Lambda environment.

## Usage

Trigger the function via HTTP requests with the appropriate JSON body. Example of a valid request body:

```json
{
    "bank": "ExampleBank",
    "merchant_name": "ExampleMerchant",
    "merchant_token": "token123",
    "cc_num": "1234567890123456",
    "security_code": "123",
    "amount": "100.00",
    "card_zip": "12345",
    "timestamp": "2021-01-01T12:00:00Z"
}
