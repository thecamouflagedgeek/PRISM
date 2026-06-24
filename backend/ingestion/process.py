def process_doc(parser, engineer_cls, path):
    raw = parser.extract(path)
    df = parser.transform(raw)

    parser.validate(df)

    engineer = engineer_cls(df)
    return engineer.build_features()