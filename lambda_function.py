import json
import boto3
import uuid
import random
from decimal import Decimal, ROUND_HALF_UP
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

DY_DB = boto3.resource('dynamodb')
TRANSACTION_TABLE = DY_DB.Table('transactions')
MERCHANT_TABLE = DY_DB.Table('merchants')
BANKS_TABLE = DY_DB.Table('banks')
BANK_FAILURE_RATE = 30

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
            
            merchant_id = get_merchant_id(merchant_name)
            
            try:
                amount = float(amount)
                cc_num = int(cc_num)
            except ValueError:
                record_transaction(merchant_name, merchant_id, cc_num, "Unknown", amount, timestamp, "error")
                return {
                    "statusCode": 404,
                    "body": json.dumps({"error": "Account not found", "details": "The specified bank or credit account does not exist"})
                }

            card_type = get_card_type(bank, cc_num)

            if not merchant_auth(merchant_name, merchant_token):
                record_transaction(merchant_name, None, cc_num, card_type, amount, timestamp, "merchant unauthorized")
                return {
                    "statusCode": 401,
                    "body": json.dumps({"error": "Unauthorized", "details": "Merchant not authorized"})
                }
            
            if (len(str(security_code)) < 3):
                record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "error")
                return {
                    "statusCode": 401,
                    "body": json.dumps({"error": "Unauthorized", "details": "Invalid security code"})
                }
    
            bank_info = get_bank_info(bank, cc_num)
            if not bank_info:
                record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "error")
                return {
                    "statusCode": 404,
                    "body": json.dumps({"error": "Account not found", "details": "The specified bank or credit account does not exist"})
                }
            
            if (card_type.lower() == "credit"):
                new_credit = verify_credit(bank_info, amount, cc_num)
                if (new_credit == "insufficient_funds"):
                    record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "declined")
                    return {
                        "statusCode": 402,
                        "body": json.dumps({"error": "Insufficient credit", "details": "Not enough available credit for this transaction"})
                    }
                elif (new_credit == "bank_failure"):
                    record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "bank failure")
                    return {
                        "statusCode": 500,
                        "body": json.dumps({"error": "Bank Error", "details": "The bank is unavailable"})
                    }
            else:
                new_balance = verify_balance(bank_info, amount, cc_num)
                if (new_balance == "insufficient_funds"):
                    record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "declined")
                    return {
                        "statusCode": 402,
                        "body": json.dumps({"error": "Insufficient funds", "details": "Not enough funds available for this transaction"})
                    }
                elif (new_balance == "bank_failure"):
                    record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "bank failure")
                    return {
                        "statusCode": 500,
                        "body": json.dumps({"error": "Bank Error", "details": "The bank is unavailable"})
                    }
            record_transaction(merchant_name, merchant_id, cc_num, card_type, amount, timestamp, "approved")
            res = {
                "statusCode": 200,
                "body": "Approved"
            }
            return res             
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
     

def merchant_auth(name, token):
    try:
        response = MERCHANT_TABLE.get_item(
            Key={
                'merchant_name': name
            }
        )
        item = response.get('Item', {})
        return item.get('token', '') == token
    except ClientError as e:
        return False

def record_transaction(name, merch_id, account, card_type, amount, timestamp, status):
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
        TRANSACTION_TABLE.put_item(Item=item)
    except Exception as e:
        print(f"Error recording transaction: {e}")

def get_merchant_id(merchant_name):
    return MERCHANT_TABLE.get_item(
    Key={
        'merchant_name': merchant_name
    }).get('Item', {}).get('id', '')

def get_card_type(bank, cc_num):
    card_type = BANKS_TABLE.get_item(
        Key={
            'bankName': bank, 
            'accountID': cc_num
        }
    )
    card_type = card_type.get('Item', {}).get('type', '')

def get_bank_info(bank, cc_num):
    response = BANKS_TABLE.query(KeyConditionExpression=Key('bankName').eq(bank) & Key('accountID').eq(cc_num))
    return response['Items'][0] if response['Items'] else None

def verify_credit(bank_info, amount, cc_num):
    credit_used = float(bank_info.get('creditUsed', 0))
    credit_limit = float(bank_info.get('creditLimit', 0))
    if credit_limit - credit_used < amount:
        return "insufficient_funds"
    new_credit_used = credit_used + amount
    new_credit_decimal = Decimal(str(new_credit_used)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if (random.randrange(0, 100) > BANK_FAILURE_RATE): 
        BANKS_TABLE.update_item(
            Key={
                'bankName': bank_info.get('bankName'),
                'accountID': cc_num
            },
            UpdateExpression='SET creditUsed = :val',
            ExpressionAttributeValues={':val': new_credit_decimal}
        )
        return True
    return "bank_failure"
    
def verify_balance(bank_info, amount, cc_num):
    balance = float(bank_info.get('balance', 0))
    if balance < amount:
        return "insufficient_funds"
    new_balance = balance - amount
    new_balance_decimal = Decimal(str(new_balance)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if (random.randrange(0, 100) > BANK_FAILURE_RATE):
        BANKS_TABLE.update_item(
            Key={
                'bankName': bank_info.get("bankName"),
                'accountID': cc_num
            },
            UpdateExpression='SET balance = :val',
            ExpressionAttributeValues={':val': new_balance_decimal}
        )
        return True
    return "bank_failure"


