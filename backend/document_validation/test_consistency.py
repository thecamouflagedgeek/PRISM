from document_validation.consistency_engine import ConsistencyEngine


def test_clean_consistency():

    engine = ConsistencyEngine()

    result = engine.assess(

        application={
            "name": "RAHUL SHARMA",
            "pan": "ABCDE1234F",
            "account_number": "1234567890",
            "monthly_income": 75000,
            "employer": "ABC LTD",
        },

        salary={
            "name": "RAHUL SHARMA",
            "pan": "ABCDE1234F",
            "net_salary": 75000,
            "employer": "ABC LTD",
        },

        bank={
            "name": "RAHUL SHARMA",
            "pan": "ABCDE1234F",
            "account_number": "1234567890",
            "average_salary_credit": 75000,
        },
    )

    assert result["status"] == "CONSISTENT"
    assert result["finding_count"] == 0


def test_name_mismatch():

    engine = ConsistencyEngine()

    result = engine.assess(

        application={
            "name": "RAHUL SHARMA",
        },

        salary={
            "name": "RAHUL KUMAR",
        },
    )

    assert result["finding_count"] == 1
    assert result["findings"][0]["rule_code"] == "CONS-001"


def test_pan_mismatch():

    engine = ConsistencyEngine()

    result = engine.assess(

        application={
            "pan": "ABCDE1234F",
        },

        salary={
            "pan": "XYZAB9876K",
        },
    )

    assert result["status"] == "CRITICAL"
    assert result["findings"][0]["rule_code"] == "CONS-002"


def test_account_mismatch():

    engine = ConsistencyEngine()

    result = engine.assess(

        application={
            "account_number": "1111111111",
        },

        bank={
            "account_number": "2222222222",
        },
    )

    assert result["finding_count"] == 1
    assert result["findings"][0]["rule_code"] == "CONS-003"


def test_income_consistent():

    engine = ConsistencyEngine()

    result = engine.assess(

        application={
            "monthly_income": 75000,
        },

        salary={
            "net_salary": 76000,
        },

        bank={
            "average_salary_credit": 74500,
        },
    )

    assert result["finding_count"] == 0


def test_income_mismatch():

    engine = ConsistencyEngine()

    result = engine.assess(

        application={
            "monthly_income": 90000,
        },

        salary={
            "net_salary": 65000,
        },

        bank={
            "average_salary_credit": 67000,
        },
    )

    assert result["finding_count"] == 1
    assert result["findings"][0]["rule_code"] == "CONS-004"


def test_employer_mismatch():

    engine = ConsistencyEngine()

    result = engine.assess(

        application={
            "employer": "ABC LTD",
        },

        salary={
            "employer": "XYZ LTD",
        },
    )

    assert result["finding_count"] == 1
    assert result["findings"][0]["rule_code"] == "CONS-005"


def test_invalid_statement_period():

    engine = ConsistencyEngine()

    result = engine.assess(

        bank={
            "statement_start_date": "2026-12-31",
            "statement_end_date": "2026-01-01",
        },
    )

    assert result["finding_count"] == 1
    assert result["findings"][0]["rule_code"] == "CONS-006"


def test_multiple_consistency_issues():

    engine = ConsistencyEngine()

    result = engine.assess(

        application={
            "name": "RAHUL SHARMA",
            "pan": "ABCDE1234F",
            "account_number": "1111111111",
            "monthly_income": 90000,
            "employer": "ABC LTD",
        },

        salary={
            "name": "RAHUL KUMAR",
            "pan": "XYZAB9876K",
            "net_salary": 60000,
            "employer": "XYZ LTD",
        },

        bank={
            "account_number": "2222222222",
            "average_salary_credit": 62000,
        },
    )

    assert result["finding_count"] >= 4
    assert result["status"] == "CRITICAL"