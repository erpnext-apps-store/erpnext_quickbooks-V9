from __future__ import unicode_literals
import frappe
from frappe import _
import frappe.defaults
import requests.exceptions
from .utils import make_quickbooks_log, pagination
from pyqb.quickbooks.batch import batch_create, batch_delete
from pyqb.quickbooks.objects.account import Account 


def sync_Account(quickbooks_obj):
	"""Fetch Account data from QuickBooks"""
	quickbooks_account_list = []
	business_objects = "Account"
	get_qb_account = pagination(quickbooks_obj, business_objects)
	if get_qb_account:
		sync_qb_accounts(get_qb_account, quickbooks_account_list)

def sync_qb_accounts(get_qb_account, quickbooks_account_list):
	quickbooks_settings = frappe.get_doc("Quickbooks Settings", "Quickbooks Settings")
	Company_abbr = frappe.db.get_value("Company", {"name": quickbooks_settings.select_company}, "abbr")
	for qb_account in get_qb_account:
		if not frappe.db.get_value("Account", {"quickbooks_account_id": qb_account.get('Id'), "company": quickbooks_settings.select_company}, "name"):
			create_account(qb_account, quickbooks_account_list, quickbooks_settings, Company_abbr)

def create_account(qb_account, quickbooks_account_list, quickbooks_settings, Company_abbr):
	""" store Account data in ERPNEXT """ 
	account = None
	account_type = None
	root_type = None
	parent_account = None

	parent_account, root_type  = account_mapper_all_country(qb_account, Company_abbr)
	
	try:	
		account = frappe.new_doc("Account")
		account.quickbooks_account_id = str(qb_account.get('Id'))
		account.account_name = str(qb_account.get('Name')) + " - " + str(qb_account.get('Id')) + " - " + "qb"
		account.is_group = False
		account.parent_account = parent_account
		set_account_type(account, qb_account)
		account.root_type = root_type
		account.account_currency = qb_account.get('CurrencyRef').get('value')
		account.company = quickbooks_settings.select_company
		account.flags.ignore_mandatory = True
		account.insert()

		frappe.db.commit()
		quickbooks_account_list.append(account.quickbooks_account_id)

	except Exception, e:
		if e.args[0] and e.args[0].startswith("402"):
			raise e
		else:
			make_quickbooks_log(title=e.message, status="Error", method="create_account", message=frappe.get_traceback(),
				request_data=qb_account, exception=True)
	
	return quickbooks_account_list

def set_account_type(account, qb_account):
	"Set account type according to Quickbooks Accounts"
	if qb_account.get('AccountType') == "Accounts Receivable":
		account.account_type = _('Receivable')
	elif qb_account.get('AccountType') == "Accounts Payable":
		account.account_type = _('Payable')
	elif qb_account.get('AccountType') == "Bank":
		account.account_type = _('Bank')

def quickbooks_accounts_head(quickbooks_settings):
	"Create account Head According to Quickbooks charts of accounts"
	chart_of_accounts = frappe.db.get_value("Company", {"name": quickbooks_settings.select_company}, "chart_of_accounts")
	if chart_of_accounts == "Singapore - F&B Chart of Accounts" or chart_of_accounts == "Singapore - Chart of Accounts":
		category_type = {'Asset, Assets':['Fixed assets','Non-current assets','Accounts receivables (Debtors)','Current assets', 'Bank'],\
					'Liability, Liabilities':['Accounts payables (Creditors)', 'Non-current liabilities', 'Current liabilities', 'Credit Cards'],\
					'Income, Income':['Other Income'],\
					'Expense, Expenses':['Other Expenses','Cost of Goods Solds']}
	else:
		category_type = {'Asset, Application of Funds (Assets)':['Fixed assets','Non-current assets','Accounts receivables (Debtors)','Current assets', 'Bank'],\
					'Liability, Source of Funds (Liabilities)':['Accounts payables (Creditors)', 'Non-current liabilities', 'Current liabilities', 'Credit Cards'],\
					'Income, Income':['Other Income'],\
					'Expense, Expenses':['Other Expenses','Cost of Goods Solds']}
	return category_type

def creates_qb_accounts_heads_to_erp_chart_of_accounts():
	quickbooks_settings = frappe.get_doc("Quickbooks Settings", "Quickbooks Settings")
	Company_abbr = frappe.db.get_value("Company", {"name": quickbooks_settings.select_company}, "abbr")
	for root_type, account_names  in quickbooks_accounts_head(quickbooks_settings).items():
		for account_name in account_names:
			if not frappe.db.get_value("Account", {"quickbooks_account_id": "Quickbooks_catagory", "name": account_name + " - qb - " + Company_abbr}, "name"):
				try:	
					qb_category_type = frappe.new_doc("Account")
					qb_category_type.quickbooks_account_id = "Quickbooks_catagory"
					qb_category_type.account_name = account_name + " - " + "qb"
					qb_category_type.is_group = True
					qb_category_type.parent_account = root_type.split(",")[1].strip() + " - " + Company_abbr
					qb_category_type.root_type = root_type.split(",")[0]
					qb_category_type.company = quickbooks_settings.select_company
					qb_category_type.flags.ignore_mandatory = True
					qb_category_type.insert()
					frappe.db.commit()
				except Exception, e:
					if e.args[0] and e.args[0].startswith("402"):
						raise e
					else:
						make_quickbooks_log(title=e.message, status="Error", method="creates_qb_accounts_heads_to_erp_chart_of_accounts", message=frappe.get_traceback(),
							request_data=account_names, exception=True)

def account_mapper_all_country(qb_account, Company_abbr):
	if qb_account.get('AccountType') == "Fixed Asset":
		parent_account = _("Fixed assets") + " - " + 'qb' + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Other Current Asset":
		parent_account = _("Current assets") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Bank":
		parent_account = _("Bank") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Other Asset":
		parent_account = _("Non-current assets") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Accounts Receivable":
		parent_account = _("Accounts receivables (Debtors)") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Accounts Payable":
		parent_account = _("Accounts payables (Creditors)") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Liability")
	elif qb_account.get('AccountType') == 'Other Current Liability':
		parent_account = _("Non-current liabilities") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Liability")
	elif qb_account.get('AccountType') == 'Long Term Liability':
		parent_account = _("Current liabilities") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Liability")
	elif qb_account.get('AccountType') == 'Credit Card':
		parent_account = _("Credit Cards") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Liability")
	elif qb_account.get("AccountType") == "Equity":
		parent_account = _("Equity") + " - " + Company_abbr
		root_type = _("Equity")
	elif qb_account.get('AccountType') == 'Income':
		parent_account = _("Direct Income") + " - " + Company_abbr
		root_type = _("Income")
	elif qb_account.get('AccountType') == 'Other Income':
		parent_account = _("Other Income") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Income")
	elif qb_account.get('AccountType') == 'Expense':
		parent_account = _("Expenses") + " - " + Company_abbr
		root_type = _("Expense")
	elif qb_account.get('AccountType') == 'Other Expense':
		parent_account = _("Other Expenses") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Expense")
	elif qb_account.get('AccountType') == 'Cost of Goods Sold':
		parent_account = _("Cost of Goods Solds") + " - " + 'qb' + " - " +  Company_abbr
		root_type = _("Expense")
	return parent_account, root_type 

def account_mapper_for_all_country(qb_account, Company_abbr):
	if qb_account.get('AccountType') == "Fixed Asset":
		parent_account = _("Fixed Assets") + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Other Current Asset":
		parent_account = _("Current Assets") + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Bank":
		parent_account = _("Bank Accounts") + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Other Asset":
		parent_account = _("Loans and Advances (Assets)") + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Accounts Receivable":
		parent_account = _("Accounts Receivable") + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Accounts Payable":
		parent_account = _("Accounts Payable") + " - " + Company_abbr
		root_type = _("Liability")
	elif qb_account.get('AccountType') == 'Other Current Liability':
		parent_account = _("Current Liabilities") + " - " + Company_abbr
		root_type = _("Liability")
	elif qb_account.get('AccountType') == 'Long Term Liability':
		parent_account = _("Loans (Liabilities)") + " - " + Company_abbr
		root_type = _("Liability")
	elif qb_account.get("AccountType") == "Equity":
		parent_account = _("Equity") + " - " + Company_abbr
		root_type = _("Equity")
	elif qb_account.get('AccountType') == 'Income':
		parent_account = _("Direct Income") + " - " + Company_abbr
		root_type = _("Income")
	elif qb_account.get('AccountType') == 'Other Income':
		parent_account = _("Indirect Income") + " - " + Company_abbr
		root_type = _("Income")
	elif qb_account.get('AccountType') == 'Expense':
		parent_account = _("Direct Expenses") + " - " + Company_abbr
		root_type = _("Expense")
	elif qb_account.get('AccountType') == 'Other Expense':
		parent_account = _("Indirect Expenses") + " - " + Company_abbr
		root_type = _("Expense")
	elif qb_account.get('AccountType') == 'Cost of Goods Sold':
		parent_account = _("Indirect Expenses") + " - " + Company_abbr
		root_type = _("Expense")
	return parent_account, root_type 

def accounts_mapper_for_singapore(qb_account, Company_abbr):
	"""Account mapper for Singapore - F&B Chart of Accounts """
	if qb_account.get('AccountType') == "Fixed Asset":
		parent_account = _("Fixed Assets") + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Other Current Asset":
		parent_account = _("Current Assets") + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Bank":
		parent_account = _("Bank Accounts") + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Other Asset":
		parent_account = _("Non-current assets") + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Accounts Receivable":
		parent_account = _("Accounts Receivable") + " - " + Company_abbr
		root_type = _("Asset")
	elif qb_account.get('AccountType') == "Accounts Payable":
		parent_account = _("Accounts Payable") + " - " + Company_abbr
		root_type = _("Liability")
	elif qb_account.get('AccountType') == 'Other Current Liability':
		parent_account = _("Non-current liabilities") + " - " + Company_abbr
		root_type = _("Liability")
	elif qb_account.get('AccountType') == 'Long Term Liability':
		parent_account = _("Accruals") + " - " + Company_abbr
		root_type = _("Liability")
	elif qb_account.get("AccountType") == "Equity":
		parent_account = _("Equity") + " - " + Company_abbr
		root_type = _("Equity")
	elif qb_account.get('AccountType') == 'Income':
		parent_account = _("Direct Income") + " - " + Company_abbr
		root_type = _("Income")
	elif qb_account.get('AccountType') == 'Other Income':
		parent_account = _("Indirect Income") + " - " + Company_abbr
		root_type = _("Income")
	elif qb_account.get('AccountType') == 'Expense':
		parent_account = _("Expenses-Direct") + " - " + Company_abbr
		root_type = _("Expense")
	elif qb_account.get('AccountType') == 'Other Expense':
		parent_account = _("Expenses-Other") + " - " + Company_abbr
		root_type = _("Expense")
	elif qb_account.get('AccountType') == 'Cost of Goods Sold':
		parent_account = _("Cost of Sales") + " - " + Company_abbr
		root_type = _("Expense")
	return parent_account, root_type

"""Sync ERPNext Account to QuickBooks"""

def sync_erp_accounts(quickbooks_obj):
	"""Recive Response From Quickbooks and Update quickbooks_account_id in Account"""
	response_from_quickbooks = sync_erp_accounts_to_quickbooks(quickbooks_obj)
	if response_from_quickbooks:
		try:
			for response_obj in response_from_quickbooks.successes:
				if response_obj:
					frappe.db.sql("""UPDATE tabAccount SET quickbooks_account_id = %s WHERE name ='%s'""" %(response_obj.Id, response_obj.Name))
					frappe.db.commit()
				else:
					raise _("Does not get any response from quickbooks")	
		except Exception, e:
			make_quickbooks_log(title=e.message, status="Error", method="sync_erp_accounts", message=frappe.get_traceback(),
				request_data=response_obj, exception=True)

def sync_erp_accounts_to_quickbooks(quickbooks_obj):
	Account_list = []
	for erp_account in erp_account_data():
		try:
			if erp_account:
				create_erp_account_to_quickbooks(erp_account, Account_list)
			else:
				raise _("Account does not exist in ERPNext")
		except Exception, e:
			if e.args[0] and e.args[0].startswith("402"):
				raise e
			else:
				make_quickbooks_log(title=e.message, status="Error", method="sync_erp_accounts_to_quickbooks", message=frappe.get_traceback(),
					request_data=erp_account, exception=True)
	results = batch_create(Account_list)
	return results

def erp_account_data():
	quickbooks_settings = frappe.get_doc("Quickbooks Settings", "Quickbooks Settings")
	erp_account = frappe.db.sql("""select name, root_type, account_type, quickbooks_account_id from `tabAccount` where is_group =0 and company='{0}' and quickbooks_account_id is NULL""".format(quickbooks_settings.select_company) ,as_dict=1)
	return erp_account

def create_erp_account_to_quickbooks(erp_account, Account_list):
	account_obj = Account()
	account_obj.Name = erp_account.name
	account_obj.FullyQualifiedName = erp_account.name
	account_classification_and_account_type(account_obj, erp_account)
	account_obj.save()
	Account_list.append(account_obj)
	return Account_list

def account_classification_and_account_type(account_obj, erp_account):
	if erp_account.root_type == "Asset":
		account_obj.Classification = erp_account.root_type
		account_obj.AccountType = "Other Current Asset"
		account_obj.AccountSubType = "AllowanceForBadDebts"
	elif erp_account.root_type =="Liability":
		account_obj.Classification = erp_account.root_type
		account_obj.AccountType = "Liability"
		account_obj.AccountSubType = "OtherCurrentLiabilities"
	elif erp_account.root_type =="Expense":
		account_obj.Classification = erp_account.root_type
		account_obj.AccountType ="Other Expense"
		account_obj.AccountSubType ="Amortization"
	elif erp_account.root_type == "Income":
		account_obj.Classification = erp_account.root_type
		account_obj.AccountType = "Income"
		account_obj.AccountSubType = "SalesOfProductIncome"
	elif erp_account.root_type == "Equity":
		account_obj.Classification = erp_account.root_type
		account_obj.AccountType = "Equity"
		account_obj.AccountSubType ="RetainedEarnings"
	else:
		account_obj.Classification = None
		account_obj.AccountType = "Cost of Goods Sold"