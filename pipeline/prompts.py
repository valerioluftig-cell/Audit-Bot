"""
Claude API prompts for extracting each of the 4 statement types.
Each prompt produces a structured JSON object.
"""

CBS_PROMPT = """You are a government finance data extraction expert. Extract ALL data from the Combined Balance Sheet of Governmental Funds from this Louisiana parish audit PDF text.

CRITICAL RULES:
1. Extract from the MAIN Balance Sheet only (not combining/nonmajor schedules)
2. Remove $ signs and commas from numbers → return plain integers
3. A dash "-" or blank means the value is null (not 0)
4. Numbers in parentheses like (123,456) are NEGATIVE: -123456
5. If the statement says "(in thousands)" set "in_thousands": true — do NOT multiply the numbers yourself; return them exactly as printed in the PDF. Our code will apply the scaling.
6. The last fund column is always "Total Governmental Funds"
7. COMPARATIVE STATEMENTS: If the PDF shows columns for two fiscal years (e.g. 2013 and 2012 side by side), extract ONLY the primary/current fiscal year column. Do NOT use values from the prior-year comparison column.

Return ONLY valid JSON (no markdown, no explanation) with this structure:

{
  "parish": "<parish name>",
  "year": <year as integer>,
  "in_thousands": <true/false>,
  "funds": ["<Fund 1>", "<Fund 2>", ..., "Total Governmental Funds"],
  "assets": {
    "cash_and_deposits": {"<Fund 1>": <int or null>, ...},
    "investments": {"<Fund 1>": <int or null>, ...},
    "taxes_receivable": {"<Fund 1>": <int or null>, ...},
    "special_assessments_receivable": {"<Fund 1>": <int or null>, ...},
    "other_receivables": {"<Fund 1>": <int or null>, ...},
    "due_from_other_governments": {"<Fund 1>": <int or null>, ...},
    "due_from_other_funds": {"<Fund 1>": <int or null>, ...},
    "due_from_component_units": {"<Fund 1>": <int or null>, ...},
    "inventory": {"<Fund 1>": <int or null>, ...},
    "prepaid_items": {"<Fund 1>": <int or null>, ...},
    "other_assets": {"<Fund 1>": <int or null>, ...},
    "total_assets": {"<Fund 1>": <int or null>, ...}
  },
  "liabilities": {
    "accounts_payable": {"<Fund 1>": <int or null>, ...},
    "retainage_payable": {"<Fund 1>": <int or null>, ...},
    "accrued_liabilities": {"<Fund 1>": <int or null>, ...},
    "deposits_payable": {"<Fund 1>": <int or null>, ...},
    "unearned_revenue": {"<Fund 1>": <int or null>, ...},
    "due_to_other_funds": {"<Fund 1>": <int or null>, ...},
    "other_liabilities": {"<Fund 1>": <int or null>, ...},
    "total_liabilities": {"<Fund 1>": <int or null>, ...}
  },
  "deferred_inflows": {
    "items": [{"label": "<description>", "values": {"<Fund 1>": <int or null>, ...}}],
    "total": {"<Fund 1>": <int or null>, ...}
  },
  "fund_balances": {
    "nonspendable": [{"label": "<description>", "values": {"<Fund 1>": <int or null>, ...}}],
    "restricted": [{"label": "<description>", "values": {"<Fund 1>": <int or null>, ...}}],
    "committed": [{"label": "<description>", "values": {"<Fund 1>": <int or null>, ...}}],
    "assigned": [{"label": "<description>", "values": {"<Fund 1>": <int or null>, ...}}],
    "unassigned": {"<Fund 1>": <int or null>, ...},
    "total_fund_balances": {"<Fund 1>": <int or null>, ...}
  },
  "total_liabilities_and_fund_balances": {"<Fund 1>": <int or null>, ...},
  "cross_sectional": {
    "cash": <General Fund value for all cash/deposit items combined>,
    "investments": <General Fund investments>,
    "receivables": <General Fund sum of taxes_receivable + special_assessments + other_receivables + due_from_other_governments>,
    "inventory": <General Fund inventory or null>,
    "other_assets": <General Fund other assets not in above categories>,
    "transfers_in": <General Fund due_from_other_funds>,
    "prepaid_items": <General Fund prepaid items or null>,
    "total_assets": <General Fund total assets>,
    "deferred_outflows": <General Fund deferred outflows of resources if present, else null>,
    "accounts_payable": <General Fund accounts_payable + retainage_payable>,
    "deferred_revenues": <General Fund unearned_revenue>,
    "government_transfers": <General Fund due_to_other_funds>,
    "other_liabilities": <General Fund accrued_liabilities + deposits_payable + other_liabilities>,
    "total_liabilities": <General Fund total liabilities>,
    "deferred_inflows": <General Fund total deferred inflows>,
    "reserved": <General Fund sum of nonspendable + restricted fund balances>,
    "unreserved_designated": <General Fund sum of committed + assigned fund balances>,
    "unreserved_undesignated": <General Fund unassigned fund balance>,
    "total_fund_balances": <General Fund total fund balances>,
    "total_liabilities_and_fund_balances": <General Fund total liabilities and fund balances>
  }
}

PDF TEXT:
"""

SOA_PROMPT = """You are a government finance data extraction expert. Extract ALL data from the Statement of Activities from this Louisiana parish audit PDF text.

CRITICAL RULES:
1. Net (Expense) Revenue values are typically shown as negative numbers
2. Remove $ signs and commas → plain integers
3. Dashes "-" = null
4. Parentheses (123,456) = negative: -123456
5. If "(in thousands)" set "in_thousands": true — do NOT multiply the numbers yourself; return them exactly as printed in the PDF. Our code will apply the scaling.
6. Extract the governmental activities section
7. COMPARATIVE STATEMENTS: If the PDF shows data for two fiscal years side by side, extract ONLY the primary/current fiscal year. Do NOT use prior-year comparison columns.

Return ONLY valid JSON (no markdown, no explanation):

{
  "parish": "<parish name>",
  "year": <year>,
  "in_thousands": <true/false>,
  "governmental_activities": {
    "general_government": {"expenses": <int or null>, "charges_for_services": <int or null>, "operating_grants": <int or null>, "capital_grants": <int or null>, "net_expense_revenue": <int or null>},
    "public_safety": {"expenses": <int or null>, "charges_for_services": <int or null>, "operating_grants": <int or null>, "capital_grants": <int or null>, "net_expense_revenue": <int or null>},
    "public_works": {"expenses": <int or null>, "charges_for_services": <int or null>, "operating_grants": <int or null>, "capital_grants": <int or null>, "net_expense_revenue": <int or null>},
    "economic_development": {"expenses": <int or null>, "charges_for_services": <int or null>, "operating_grants": <int or null>, "capital_grants": <int or null>, "net_expense_revenue": <int or null>},
    "health_and_welfare": {"expenses": <int or null>, "charges_for_services": <int or null>, "operating_grants": <int or null>, "capital_grants": <int or null>, "net_expense_revenue": <int or null>},
    "culture_and_recreation": {"expenses": <int or null>, "charges_for_services": <int or null>, "operating_grants": <int or null>, "capital_grants": <int or null>, "net_expense_revenue": <int or null>},
    "interest_on_long_term_debt": {"expenses": <int or null>, "net_expense_revenue": <int or null>},
    "other_activities": [{"label": "<name>", "expenses": <int or null>, "charges_for_services": <int or null>, "operating_grants": <int or null>, "capital_grants": <int or null>, "net_expense_revenue": <int or null>}],
    "total": {"expenses": <int or null>, "charges_for_services": <int or null>, "operating_grants": <int or null>, "capital_grants": <int or null>, "net_expense_revenue": <int or null>}
  },
  "general_revenues": {
    "property_taxes": <int or null>,
    "sales_taxes": <int or null>,
    "severance_taxes": <int or null>,
    "fire_insurance_premiums": <int or null>,
    "franchise_fees": <int or null>,
    "other_taxes": <int or null>,
    "occupational_licenses": <int or null>,
    "gaming_revenues": <int or null>,
    "state_revenue_sharing": <int or null>,
    "state_shared_revenue": <int or null>,
    "non_employer_pension_contribution": <int or null>,
    "investment_income": <int or null>,
    "miscellaneous": <int or null>,
    "transfers": <int or null>,
    "other_items": [{"label": "<name>", "amount": <int or null>}],
    "total_general_revenues": <int or null>
  },
  "change_in_net_position": <int or null>,
  "net_position_beginning": <int or null>,
  "net_position_ending": <int or null>,
  "cross_sectional": {
    "property_ad_valorem": <property taxes total>,
    "sales_use_taxes": <sales taxes + gaming revenues combined>,
    "severance_taxes": <severance taxes>,
    "other_tax_revenue": <fire insurance + franchise fees + occupational licenses + other taxes>,
    "total_tax_revenue": <sum of all tax revenues>,
    "state_revenue_sharing": <state revenue sharing>,
    "state_intergovernmental": <state grants from program revenues operating + capital>,
    "federal_intergovernmental": <federal grants from program revenues>,
    "local_transfer": <transfers amount>,
    "all_other_revenue": <investment income + miscellaneous + other>,
    "total_other_revenue": <state_revenue_sharing + intergovernmental + transfers + other>,
    "total_program_revenue": <charges_for_services + operating_grants + capital_grants from total govt activities>,
    "total_revenues": <total_tax_revenue + total_other_revenue + total_program_revenue>,
    "general_government": <total general government net expense revenue>,
    "legislative": null,
    "judicial": null,
    "elections": null,
    "finance_and_administration": null,
    "other_general_government": null,
    "total_general_government": <general government net expense revenue>,
    "public_safety": <public safety net expense revenue>,
    "public_works": <public works net expense revenue>,
    "economic_development": <economic development net expense revenue>,
    "health_and_welfare": <health and welfare net expense revenue>,
    "culture_and_recreation": <culture and recreation net expense revenue>,
    "interest_debt_service": <interest on long term debt net expense revenue>,
    "all_other_expenditures": <other activities net expense revenue total>,
    "total_expenditures": <total governmental activities expenses>
  }
}

PDF TEXT:
"""

SONA_PROMPT = """You are a government finance data extraction expert. Extract ALL data from the Statement of Net Position (or Statement of Net Assets) from this Louisiana parish audit PDF text.

CRITICAL RULES:
1. Remove $ signs and commas → plain integers
2. Dashes "-" = null
3. Parentheses (123,456) = negative: -123456
4. If "(in thousands)" set "in_thousands": true — do NOT multiply the numbers yourself; return them exactly as printed in the PDF. Our code will apply the scaling.
5. Extract the government-wide statement (Governmental Activities column)
6. COMPARATIVE STATEMENTS: If the PDF shows columns for two fiscal years (e.g. 2013 and 2012 side by side), extract ONLY the primary/current fiscal year column. Do NOT use values from the prior-year comparison column.

Return ONLY valid JSON (no markdown, no explanation):

{
  "parish": "<parish name>",
  "year": <year>,
  "in_thousands": <true/false>,
  "governmental_activities": {
    "current_assets": {
      "cash_and_deposits": <int or null>,
      "investments": <int or null>,
      "taxes_receivable": <int or null>,
      "other_receivables": <int or null>,
      "due_from_other_governments": <int or null>,
      "due_from_component_units": <int or null>,
      "inventory": <int or null>,
      "prepaid_items": <int or null>,
      "other_current_assets": <int or null>
    },
    "capital_assets": {
      "non_depreciable": <int or null>,
      "depreciable_net": <int or null>,
      "right_to_use_net": <int or null>,
      "total_capital_assets_net": <int or null>
    },
    "other_noncurrent_assets": <int or null>,
    "total_assets": <int or null>,
    "deferred_outflows": {
      "items": [{"label": "<description>", "amount": <int or null>}],
      "total": <int or null>
    },
    "current_liabilities": {
      "accounts_payable": <int or null>,
      "retainage_payable": <int or null>,
      "accrued_liabilities": <int or null>,
      "deposits_payable": <int or null>,
      "unearned_revenue": <int or null>,
      "accrued_interest": <int or null>,
      "other_current_liabilities": <int or null>
    },
    "long_term_liabilities": {
      "bonds_payable_current": <int or null>,
      "bonds_payable_noncurrent": <int or null>,
      "compensated_absences_current": <int or null>,
      "compensated_absences_noncurrent": <int or null>,
      "net_pension_liability": <int or null>,
      "landfill_closure": <int or null>,
      "lease_liability_current": <int or null>,
      "lease_liability_noncurrent": <int or null>,
      "other_long_term": <int or null>
    },
    "total_liabilities": <int or null>,
    "deferred_inflows": {
      "items": [{"label": "<description>", "amount": <int or null>}],
      "total": <int or null>
    },
    "net_position": {
      "net_investment_in_capital_assets": <int or null>,
      "restricted": <int or null>,
      "unrestricted": <int or null>,
      "total_net_position": <int or null>
    }
  },
  "component_units": {
    "total_assets": <int or null>,
    "total_liabilities": <int or null>,
    "total_net_position": <int or null>
  }
}

PDF TEXT:
"""

CA_PROMPT = """You are a government finance data extraction expert. Extract ALL data from the Capital Assets schedule from this Louisiana parish audit PDF text.

CRITICAL RULES:
1. Remove $ signs and commas → plain integers
2. Dashes "-" = null
3. Parentheses (123,456) = negative: -123456
4. If "(in thousands)" set "in_thousands": true — do NOT multiply the numbers yourself; return them exactly as printed in the PDF. Our code will apply the scaling.
5. Decreases/disposals are typically shown as negative numbers
6. Extract Governmental Activities section
7. COMPARATIVE STATEMENTS: If the PDF shows beginning/ending data spanning two fiscal years or compares two years side by side, extract ONLY the current fiscal year's data. The "beginning" balance is the opening balance for the current year (= prior year ending).

Return ONLY valid JSON (no markdown, no explanation):

{
  "parish": "<parish name>",
  "year": <year>,
  "in_thousands": <true/false>,
  "governmental_activities": {
    "not_depreciated": {
      "land": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "construction_in_progress": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "other_non_depreciable": [{"label": "<name>", "beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>}],
      "total_not_depreciated": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>}
    },
    "depreciable": {
      "buildings_and_improvements": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "machinery_and_equipment": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "improvements_other_than_buildings": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "infrastructure": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "vehicles": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "furniture_and_fixtures": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "books_and_periodicals": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "leased_property": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "other_depreciable": [{"label": "<name>", "beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>}],
      "total_depreciable": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>}
    },
    "accumulated_depreciation": {
      "buildings_and_improvements": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "machinery_and_equipment": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "improvements_other_than_buildings": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "infrastructure": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "vehicles": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "furniture_and_fixtures": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "books_and_periodicals": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "leased_property": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
      "other": [{"label": "<name>", "beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>}],
      "total_accumulated_depreciation": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>}
    },
    "total_depreciable_net": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>},
    "total_capital_assets_net": {"beginning": <int or null>, "increases": <int or null>, "decreases": <int or null>, "ending": <int or null>}
  },
  "cross_sectional": {
    "land": <ending balance for land>,
    "construction_in_progress": <ending balance for CIP>,
    "other_non_depreciable": <ending balance for other non-depreciable>,
    "buildings_net": <buildings ending gross minus accumulated depreciation>,
    "improvements_net": <improvements net>,
    "machinery_net": <machinery net>,
    "other_depreciable_net": <other depreciable net (books, furniture, leased, other)>,
    "vehicles_net": <vehicles net>,
    "bridges_net": <bridges net if applicable>,
    "leased_property_net": <leased property net>,
    "infrastructure_net": <infrastructure net>,
    "total_governmental_net": <total capital assets net - governmental activities ending balance>
  }
}

PDF TEXT:
"""
