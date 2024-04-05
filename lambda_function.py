import json
import boto3
import uuid
import random
from decimal import Decimal, ROUND_HALF_UP
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr

def lambda_handler(event, context):
    response = {}
    if 'body' in event and event['body'] is not None:
        try:
            body = json.loads(event['body'])
            bank = body.get('bank')
            merchant_name = body.get('merchant_name')
            merchant_token = body.get('merchant_token')
            cc_num = body.get('cc_num')
            security_code = body.get('security_code')
            amount = body.get('amount')
            card_zip = body.get('card_zip')
            timestamp = body.get('timestamp')
            
            if None in [bank, merchant_name, cc_num, merchant_token, security_code, amount, card_zip, timestamp]:
                raise ValueError("Please enter all fields")
            
            dynamo_db = boto3.resource('dynamodb')
            
            transaction_table = dynamo_db.Table('transactions')
            
            merchant_table = dynamo_db.Table('merchants')
            banks_table = dynamo_db.Table('banks')
            
            merchant_id = merchant_table.get_item(
                Key={
                    'merchant_name': merchant_name
                }).get('Item', {}).get('id', '')
            
            try:
                amount = float(amount)
                cc_num = int(cc_num)
            except ValueError:
                record_transaction(merchant_name, merchant_id, cc_num, "Unknown", amount, timestamp, "error", transaction_table)
                return {
                    "statusCode": 404,
                    "body": json.dumps({"error": "Account not found", "details": "The specified bank or credit account does not exist"})
                }

            card_type = banks_table.get_item(
                Key={
                    'bankName': bank, 
                    'accountID': cc_num
                }
            )
            card_type = card_type.get('Item', {}).get('type', '')

            if not merchant_auth(merchant_name, merchant_token, merchant_table):
                record_transaction(merchant_name, None, cc_num, card_type, amount, timestamp, "merchant unauthorized", transaction_table)
                return {
                    "statusCode": 401,
                    "body": json.dumps({"error": "Unauthorized", "details": "Merchant not authorized"})
                }
            
            
            
            if (len(str(security_code)) < 3):
                record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "error", transaction_table)
                return {
                    "statusCode": 401,
                    "body": json.dumps({"error": "Unauthorized", "details": "Invalid security code"})
                }
    
            response = banks_table.query(KeyConditionExpression=Key('bankName').eq(bank) & Key('accountID').eq(cc_num))
            bank_info = response['Items'][0] if response['Items'] else None
            if not bank_info:
                record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "error", transaction_table)
                return {
                    "statusCode": 404,
                    "body": json.dumps({"error": "Account not found", "details": "The specified bank or credit account does not exist"})
                }
            
            if (card_type.lower() == "credit"):
                credit_used = float(bank_info.get('creditUsed', 0))
                credit_limit = float(bank_info.get('creditLimit', 0))
                if credit_limit - credit_used < amount:
                    record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "declined", transaction_table)
                    return {
                        "statusCode": 402,
                        "body": json.dumps({"error": "Insufficient credit", "details": "Not enough available credit for this transaction"})
                    }
    
                new_credit_used = credit_used + amount
                new_credit_decimal = Decimal(str(new_credit_used)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                bank_failure_rate = 30
                if (random.randrange(0, 100) > bank_failure_rate): 
                    banks_table.update_item(
                        Key={
                            'bankName': bank,
                            'accountID': cc_num
                        },
                        UpdateExpression='SET creditUsed = :val',
                        ExpressionAttributeValues={':val': new_credit_decimal}
                    )
                else:
                    record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "bank failure", transaction_table)
                    return {
                        "statusCode": 500,
                        "body": json.dumps({"error": "Bank Error", "details": "The bank is unavailable"})
                    }
            else:
                balance = float(bank_info.get('balance', 0))
                if balance < amount:
                    record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "declined", transaction_table)
                    return {
                        "statusCode": 402,
                        "body": json.dumps({"error": "Insufficient funds", "details": "Not enough funds available for this transaction"})
                    }
                new_balance = balance - amount
                new_balance_decimal = Decimal(str(new_balance)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                banks_table.update_item(
                    Key={
                        'bankName': bank,
                        'accountID': cc_num
                    },
                    UpdateExpression='SET balance = :val',
                    ExpressionAttributeValues={':val': new_balance_decimal}
                )
            
        except json.JSONDecodeError as e:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid JSON format", "details": str(e)})
            }
        except KeyError as e:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Missing key in JSON", "details": str(e)})
            }
        except Exception as e:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "An error occurred", "details": str(e)})
            }
        except:
            return {
                "statusCode": 400,
                "body": "Please format your request properly"
            }
    else:
        return {
                "statusCode": 400,
                "body": json.dumps({"error": "An error occurred", "details": "Your request is not formatted correctly"})
            }
    
    record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "approved", transaction_table)
    res = {
        "statusCode": 200,
        "body": "Approved"
    }
    return res
    

def merchant_auth(name, token, table):
    try:
        response = table.get_item(
            Key={
                'merchant_name': name
            }
        )
        item = response.get('Item', {})
        return item.get('token', '') == token
    except ClientError as e:
        return False


def record_transaction(name, merch_id, account, card_type, amount, timestamp, status, table):
    amount = Decimal("{:.2f}".format(float(amount)))
    account = str(account)
    account = account[-4:]
    merch_id = str(merch_id) if merch_id is not None else ''
    item = {
        'id': str(uuid.uuid4()),
        'account': account,
        'merchant_name': name,
        'merchant_id': merch_id,
        'card_type': card_type,
        'amount': amount,
        'timestamp': timestamp,
        'status': status
    }
    print(item)
    try:
        table.put_item(Item=item)
    except Exception as e:
        print(f"Error recording transaction: {e}")
