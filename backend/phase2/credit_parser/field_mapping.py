"""Single explicit field mapping for the controlled statement source format."""
STATEMENT_FIELDS={"account_reference":"account_reference","provider":"provider","masked_account_number":"masked_account_number","currency":"currency","month":"statement_month","balance":"statement_balance","payment":"payment_amount","status":"repayment_status","metadata":"source_metadata"}
REPAYMENT_FIELDS={"account_reference":"account_reference","provider":"provider","product":"product_type","month":"month","status":"repayment_status","severity":"delinquency_severity","metadata":"source_metadata"}
TEXT_LABELS={
 "STATEMENT MONTH":"statement_month", "BILLING MONTH":"statement_month",
 "STATEMENT DATE":"statement_month", "BILLING DATE":"statement_month",
 "ACCOUNT REFERENCE":"account_reference", "CARD ACCOUNT":"account_reference",
 "PROVIDER":"provider", "ISSUER":"provider",
 "ACCOUNT":"masked_account_number", "CARD NUMBER":"masked_account_number",
 "CARD NO":"masked_account_number", "CURRENCY":"currency",
 "STATEMENT BALANCE":"statement_balance", "BILLED BALANCE":"statement_balance",
 "NEW BALANCE":"statement_balance", "TOTAL NEW BALANCE":"statement_balance",
 "PAYMENT APPLIED TO STATEMENT":"payment_amount",
 "PAYMENT RECEIVED":"payment_amount",
 "PAYMENT RECEIVED FOR STATEMENT":"payment_amount",
 "REPAYMENT STATUS":"status", "PAYMENT STATUS":"status",
 "DELINQUENCY LEVEL":"delinquency_severity", "DELINQUENCY SEVERITY":"delinquency_severity",
}
