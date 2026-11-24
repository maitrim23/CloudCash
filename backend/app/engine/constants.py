"""Time constants.

Recovered from the AWS Pricing Calculator's own constants table (found by reading the
bundle the calculator serves to browsers):

    HOURS_IN_DAY 24, HOURS_IN_MONTH 730, TOTAL_MONTHS 12,
    AVG_WEEKS_IN_MONTH 4.345238095238095, HOURS_PER_WEEK 168

A "month" is *always* 730 hours (= 8760 hours / 12), regardless of the calendar.
"""

from decimal import Decimal

HOURS_IN_DAY = Decimal(24)
HOURS_IN_MONTH = Decimal(730)
MONTHS_IN_YEAR = Decimal(12)
DAYS_IN_WEEK = Decimal(7)
# 365 / 7 / 12 = 4.345238095238095...  Kept as the calculator's literal value.
AVG_WEEKS_IN_MONTH = Decimal("4.345238095238095")

# S3 tier boundaries in AWS price files are expressed in GB where 1 TB = 1024 GB
# (e.g. the Standard class changes price at 51200 GB == 50 TB).
GB_PER_TB = Decimal(1024)
