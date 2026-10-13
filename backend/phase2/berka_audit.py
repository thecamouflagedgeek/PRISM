"""Read-only Berka/PKDD'99 Phase 2A audit. No model fitting or production imports."""
from __future__ import annotations
import csv, json, math, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from phase2.windowing import complete_calendar_window

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "berka"
OUT = ROOT / "outputs" / "berka_audit"
OUT.mkdir(parents=True, exist_ok=True)
EXPECTED = ["account.asc", "card.asc", "client.asc", "disp.asc", "district.asc", "loan.asc", "order.asc", "trans.asc"]

def load(path):
    with path.open("r", encoding="latin1", newline="") as f:
        head = f.readline()
    return pd.read_csv(path, sep=";" if ";" in head else ",", quotechar='"', dtype="string", encoding="latin1", keep_default_na=False, on_bad_lines="error")

def num(df):
    out = df.copy()
    for c in out:
        vals = pd.to_numeric(out[c].replace("", pd.NA), errors="coerce")
        if vals.notna().sum() and vals.notna().sum() >= max(1, int(out[c].replace("", pd.NA).notna().sum() * .9)):
            out[c] = vals
    return out

def dte(s):
    x = pd.to_numeric(s.astype("string").str.slice(0, 6), errors="coerce")
    yy, mm, dd = (x // 10000).astype("Int64"), ((x // 100) % 100).astype("Int64"), (x % 100).astype("Int64")
    return pd.to_datetime(dict(year=1900 + yy, month=mm, day=dd), errors="coerce")

def j(v):
    if pd.isna(v): return None
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating, float)): return float(v) if math.isfinite(float(v)) else None
    return str(v)

def main():
    present = sorted(p.name for p in DATA.iterdir() if p.is_file())
    raw = {p.stem: load(p) for p in DATA.glob("*.asc")}
    t = {k: num(v) for k, v in raw.items()}
    dates = {"account": "date", "loan": "date", "trans": "date", "card": "issued"}
    audit = {"source_files_present": present, "expected_asc_files": EXPECTED, "missing_expected_files": [x for x in EXPECTED if x not in present], "tables": {}}
    keycols = {"account":"account_id", "card":"card_id", "client":"client_id", "disp":"disp_id", "district":"A1", "loan":"loan_id", "order":"order_id", "trans":"trans_id"}
    for name, df in raw.items():
        a = {"filename": name + ".asc", "delimiter": "semicolon", "rows": len(df), "columns": len(df.columns), "column_names": list(df.columns), "inferred_types": {}, "missing_by_column": {}, "duplicate_rows": int(df.duplicated().sum()), "unique_values": {}, "numeric_ranges": {}, "date_ranges": {}, "key_checks": {}, "obvious_anomalies": {}}
        for c in df:
            s = df[c].replace("", pd.NA); n = pd.to_numeric(s, errors="coerce")
            if c == dates.get(name):
                dt = dte(df[c]); a["inferred_types"][c] = "date YYMMDD"; a["date_ranges"][c] = {"min": j(dt.min()), "max": j(dt.max()), "invalid_count": int(dt.isna().sum())}
            elif s.notna().sum() and n.notna().sum() >= max(1, int(s.notna().sum() * .9)):
                a["inferred_types"][c] = "numeric"; a["numeric_ranges"][c] = {"min": j(n.min()), "max": j(n.max())}
            else:
                a["inferred_types"][c] = "categorical" if s.nunique() <= 100 else "string/identifier-like"
                if s.nunique() <= 100: a["unique_values"][c] = {str(k): int(v) for k, v in s.value_counts(dropna=False).items()}
            a["missing_by_column"][c] = int(s.isna().sum())
        key = keycols[name]
        s = df[key].replace("", pd.NA)
        a["key_checks"][key] = {"null": int(s.isna().sum()), "distinct": int(s.nunique()), "duplicate_nonnull": int(s.duplicated().sum())}
        numeric=pd.DataFrame({c:pd.to_numeric(df[c],errors="coerce") for c in df.columns})
        for c in ["amount","payments","duration","balance"]:
            if c in numeric:
                bad=numeric[c]<0
                a["obvious_anomalies"][f"negative_{c}"]={"count":int(bad.sum()),"row_indexes_sample":df.index[bad].tolist()[:20]}
        if name=="loan":
            bad=dte(df["date"]).isna(); a["obvious_anomalies"]["invalid_dates"]={"count":int(bad.sum()),"row_indexes_sample":df.index[bad].tolist()[:20]}
            unknown=~df.status.isin(["A","B","C","D"]); a["obvious_anomalies"]["unknown_status"]={"count":int(unknown.sum()),"values":df.loc[unknown,"status"].unique().tolist()[:20]}
        if name=="trans":
            unknown=~df.type.isin(["PRIJEM","VYDAJ","VYBER KARTOU"]); a["obvious_anomalies"]["unknown_transaction_type"]={"count":int(unknown.sum()),"values":df.loc[unknown,"type"].value_counts().head(20).to_dict()}
            bad=dte(df["date"]).isna(); a["obvious_anomalies"]["invalid_dates"]={"count":int(bad.sum()),"row_indexes_sample":df.index[bad].tolist()[:20]}
        audit["tables"][name] = a
    (OUT / "dataset_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    for k, c in dates.items(): t[k]["parsed_date"] = dte(raw[k][c])
    A, C, D, DI, L, O, X = (t[k] for k in ("account", "client", "disp", "district", "loan", "order", "trans"))
    rel = {"counts": {k: len(v) for k, v in t.items()}, "relationships": {"client-to-account": "client.client_id -> disp.client_id -> disp.account_id -> account.account_id", "loan-to-history": "loan.account_id -> account.account_id -> trans.account_id; join transactions with trans.date < loan.date", "card": "card.disp_id -> disp.disp_id", "orders": "order.account_id -> account.account_id", "district": "account/client.district_id -> district.A1"}, "guide_status_semantics": {"A":"contract finished, no problems", "B":"contract finished, loan not paid", "C":"running contract, OK so far", "D":"running contract, client in debt"}, "status_counts": {str(k): int(v) for k,v in L.status.value_counts().items()}, "orphan_checks": {}, "multiplicity": {}}
    def orphan(ch, cc, par, pc):
        cs, ps = set(pd.to_numeric(ch[cc], errors="coerce").dropna().astype(int)), set(pd.to_numeric(par[pc], errors="coerce").dropna().astype(int))
        return {"orphan_count": len(cs-ps), "orphan_ids_sample": sorted(cs-ps)[:20]}
    for tn, cc, pn, pc in [("disp","client_id","client","client_id"),("disp","account_id","account","account_id"),("trans","account_id","account","account_id"),("loan","account_id","account","account_id"),("order","account_id","account","account_id"),("card","disp_id","disp","disp_id"),("account","district_id","district","A1"),("client","district_id","district","A1")]: rel["orphan_checks"][tn+"."+cc] = orphan(t[tn],cc,t[pn],pc)
    owners = D[D.type.str.upper()=="OWNER"]
    rel["multiplicity"] = {"accounts_with_multiple_owners": int((owners.groupby("account_id").client_id.nunique()>1).sum()), "accounts_with_multiple_loans": int((L.groupby("account_id").size()>1).sum()), "clients_with_multiple_accounts": int((D.groupby("client_id").account_id.nunique()>1).sum()), "duplicate_client_account_relationships": int(D.duplicated(["client_id","account_id"]).sum()), "loans_without_transactions": int((~L.account_id.isin(X.account_id)).sum()), "transactions_without_account": int((~X.account_id.isin(A.account_id)).sum())}
    (OUT / "relational_integrity.json").write_text(json.dumps(rel, indent=2), encoding="utf-8")

    status = L.groupby("status").agg(count=("loan_id","size"), amount_mean=("amount","mean"), amount_median=("amount","median"), amount_min=("amount","min"), amount_max=("amount","max"), duration_mean=("duration","mean"), duration_median=("duration","median"), duration_min=("duration","min"), duration_max=("duration","max"), payment_mean=("payments","mean"), payment_median=("payments","median"), payment_min=("payments","min"), payment_max=("payments","max")).reset_index()
    loan_dates=dte(raw["loan"].date); status_dates=pd.DataFrame({"status":L.status,"loan_date":loan_dates}).groupby("status").loan_date.agg(loan_date_min="min",loan_date_max="max").reset_index(); status=status.merge(status_dates,on="status")
    status["percentage"] = 100 * status["count"] / len(L)
    status["documented_semantics"] = status.status.map(rel["guide_status_semantics"])
    status["strict_target"] = status.status.map({"A":"Y=0 successful matured", "B":"Y=1 unsuccessful matured", "C":"exclude unresolved running", "D":"exclude unresolved running delinquency"})
    status.to_csv(OUT / "loan_target_analysis.csv", index=False)

    X["parsed_date"] = dte(raw["trans"].date); L["parsed_date"] = dte(raw["loan"].date)
    A["opened_date"] = dte(raw["account"].date)
    source_start = X.parsed_date.min()
    source_end_exclusive = (X.parsed_date.max().to_period("M") + 1).start_time.date()
    X["amount"] = pd.to_numeric(X.amount, errors="coerce"); X["balance"] = pd.to_numeric(X.balance, errors="coerce")
    txmap = {int(k): g.sort_values("parsed_date") for k,g in X.groupby("account_id")}
    temporal=[]; monthly=[]; features=[]; window_reconciliation=[]
    for r in L.itertuples(index=False):
        aid=int(r.account_id); ld=r.parsed_date; g=txmap.get(aid, X.iloc[:0]); pre=g[g.parsed_date<ld] if pd.notna(ld) else g.iloc[:0]; post=g[g.parsed_date>=ld] if pd.notna(ld) else g.iloc[:0]
        first=pre.parsed_date.min() if len(pre) else pd.NaT; last=pre.parsed_date.max() if len(pre) else pd.NaT
        opened=A.loc[A.account_id==aid,"opened_date"]
        opened=opened.iloc[0] if len(opened) else pd.NaT
        temporal.append({"loan_id":int(r.loan_id),"account_id":aid,"status":str(r.status),"target":1 if r.status=="B" else (0 if r.status=="A" else ""),"loan_date":j(ld),"account_open_date":j(opened),"first_preloan_transaction":j(first),"last_preloan_transaction":j(last),"months_preloan_history":(ld-first).days/30.4375 if pd.notna(first) and pd.notna(ld) else np.nan,"preloan_transaction_count":len(pre),"preloan_UVER_payment_count":int((pre.k_symbol=="UVER").sum()),"postloan_transaction_count":len(post),"postloan_UVER_payment_count":int((post.k_symbol=="UVER").sum()),"postloan_history_overlaps_repayment":bool((post.k_symbol=="UVER").any())})
        for w in (3,6,12,None):
            tag=f"{w}m" if w else "all_preloan"
            label=1 if r.status=="B" else (0 if r.status=="A" else np.nan)
            cw=complete_calendar_window(ld.to_pydatetime(),w,account_open_date=opened.date() if pd.notna(opened) else None,source_coverage_start=source_start.date(),source_coverage_end_exclusive=source_end_exclusive) if w and pd.notna(ld) else None
            window_start=pd.Timestamp(cw.window_start) if cw else pd.NaT
            window_end=pd.Timestamp(cw.window_end_exclusive) if cw else pd.NaT
            p=pre[(pre.parsed_date>=window_start)&(pre.parsed_date<window_end)] if w and pd.notna(ld) else (pre if not w else pre.iloc[:0])
            den=w if w else max(1,((ld.to_period("M")-first.to_period("M")).n+1) if pd.notna(ld) and pd.notna(first) else 1)
            full_coverage=bool(cw and cw.eligible)
            if w and label in (0,1):
                old_start=ld-pd.DateOffset(months=w)
                old_eligible=bool(pd.notna(opened) and opened<=old_start and old_start>=source_start)
                window_reconciliation.append({"loan_id":int(r.loan_id),"account_id":aid,"status":str(r.status),"target":int(label),"window":tag,"old_rolling_start":old_start.date().isoformat(),"new_calendar_start":cw.window_start.isoformat(),"window_end_exclusive":cw.window_end_exclusive.isoformat(),"old_rolling_eligible":old_eligible,"new_calendar_eligible":cw.eligible,"new_coverage_state":cw.coverage_state,"reconciliation_status":"SUPERSEDED_WINDOW_DEFINITION" if old_eligible and not cw.eligible else "UNCHANGED_MEMBERSHIP"})
            if w and pd.notna(ld):
                month_index=pd.period_range(window_start.to_period("M"), (window_end-pd.Timedelta(days=1)).to_period("M"),freq="M")
            if len(p):
                p=p.copy(); p["month"]=p.parsed_date.dt.to_period("M"); p["credit"]=np.where(p.type.str.upper()=="PRIJEM",p.amount,0.); p["debit"]=np.where(p.type.str.upper().isin(["VYDAJ","VYBER KARTOU"]),p.amount,0.); p["net"]=p.credit-p.debit; p["is_credit"]=(p.type.str.upper()=="PRIJEM").astype(int); p["is_debit"]=(p.type.str.upper().isin(["VYDAJ","VYBER KARTOU"])).astype(int)
                m=p.groupby("month").agg(credits=("credit","sum"),debits=("debit","sum"),net=("net","sum"),txn=("trans_id","count"),credit_count=("is_credit","sum"),debit_count=("is_debit","sum"),bal_min=("balance","min"),bal_max=("balance","max"),bal_mean=("balance","mean"),bal_end=("balance","last"))
                if w and pd.notna(ld):
                    m=m.reindex(month_index)
                    m[["credits","debits","net","txn","credit_count","debit_count"]]=m[["credits","debits","net","txn","credit_count","debit_count"]].fillna(0)
                if w in (3,6) and label in (0,1) and full_coverage:
                    event_groups={mon:events for mon,events in p.groupby("month",sort=False)}
                    for mon,z in m.iterrows():
                        events=event_groups.get(mon,p.iloc[:0])
                        first_event=events.sort_values("parsed_date").iloc[0] if len(events) else None
                        delta=(float(first_event.amount) if str(first_event.type).upper()=="PRIJEM" else (-float(first_event.amount) if str(first_event.type).upper() in ["VYDAJ","VYBER KARTOU"] else 0.)) if first_event is not None and pd.notna(first_event.amount) else np.nan
                        opening_approx=float(first_event.balance)-delta if first_event is not None and pd.notna(first_event.balance) and pd.notna(delta) else np.nan
                        monthly.append({"loan_id":int(r.loan_id),"account_id":aid,"window":tag,"month":str(mon),**{k:j(v) for k,v in z.items()},"opening_balance_approx":opening_approx,"transaction_type_counts_json":json.dumps({str(k):int(v) for k,v in events.type.value_counts(dropna=False).items()},ensure_ascii=False),"transaction_category_amounts_json":json.dumps({str(k):float(v) for k,v in events.groupby(events.k_symbol.fillna("").replace("","(blank)" )).amount.sum().items()},ensure_ascii=False)})
                net=m.net.astype(float); cr=m.credits.astype(float); db=m.debits.astype(float); bal=pd.to_numeric(p.balance,errors="coerce").dropna(); sd=float(net.std(ddof=1)) if len(net)>1 else np.nan; mn=float(net.mean()) if len(net) else np.nan
                vals={"avg_monthly_credit":float(cr.sum()/den),"avg_monthly_debit":float(db.sum()/den),"credit_debit_ratio":float(cr.sum()/db.sum()) if db.sum()>0 else np.nan,"avg_monthly_net_cashflow":float(net.sum()/den),"cashflow_std":sd,"cashflow_cv":sd/abs(mn) if pd.notna(sd) and mn!=0 else np.nan,"positive_cashflow_month_ratio":float((net>0).sum()/den),"negative_cashflow_month_ratio":float((net<0).sum()/den),"negative_cashflow_month_count":int((net<0).sum()),"inflow_trend":float(np.polyfit(np.arange(len(cr)),cr,1)[0]) if len(cr)>1 else np.nan,"outflow_trend":float(np.polyfit(np.arange(len(db)),db,1)[0]) if len(db)>1 else np.nan,"avg_balance":bal.mean(),"min_balance":bal.min(),"max_balance":bal.max(),"balance_std":bal.std(ddof=1),"balance_cv":bal.std(ddof=1)/abs(bal.mean()) if len(bal)>1 and bal.mean()!=0 else np.nan,"low_balance_frequency":float((bal<=0).mean()) if len(bal) else np.nan,"negative_balance_frequency":float((bal<0).mean()) if len(bal) else np.nan,"end_of_month_balance_trend":float(np.polyfit(np.arange(m.bal_end.dropna().size),m.bal_end.dropna(),1)[0]) if m.bal_end.notna().sum()>1 else np.nan,"transaction_count":len(p),"median_count_months":m.txn.median()}
                ks=p.k_symbol.fillna("").str.upper(); pension=p[(ks=="DUCHOD")&(p.type.str.upper()=="PRIJEM")].copy(); pension["month"]=pension.parsed_date.dt.to_period("M"); pension_month=pension.groupby("month").amount.sum().reindex(m.index,fill_value=0) if len(pension) else pd.Series(0.,index=m.index)
                vals["documented_pension_credit_total"]=float(pension.amount.sum()); vals["pension_credit_month_ratio"]=float((pension_month>0).sum()/den); vals["pension_credit_cv"]=float(pension_month.std(ddof=1)/abs(pension_month.mean())) if len(pension_month)>1 and pension_month.mean()!=0 else np.nan
                vals["documented_loan_payment_total"]=float(p.loc[ks=="UVER","amount"].sum()); vals["documented_insurance_payment_total"]=float(p.loc[ks=="POJISTNE","amount"].sum()); vals["documented_household_payment_total"]=float(p.loc[ks=="SIPO","amount"].sum())
            else:
                vals={k:np.nan for k in ["avg_monthly_credit","avg_monthly_debit","credit_debit_ratio","avg_monthly_net_cashflow","cashflow_std","cashflow_cv","positive_cashflow_month_ratio","negative_cashflow_month_ratio","negative_cashflow_month_count","inflow_trend","outflow_trend","avg_balance","min_balance","max_balance","balance_std","balance_cv","low_balance_frequency","negative_balance_frequency","end_of_month_balance_trend","documented_pension_credit_total","pension_credit_month_ratio","pension_credit_cv","documented_loan_payment_total","documented_insurance_payment_total","documented_household_payment_total"]}; vals.update(transaction_count=0,median_count_months=np.nan)
            all_history_covered=bool(pd.notna(opened) and opened>=source_start)
            eligible=bool(label in (0,1) and (full_coverage if w else len(p)>0))
            if w and not full_coverage:
                vals={k:(v if k=="transaction_count" else np.nan) for k,v in vals.items()}
            features.append({"loan_id":int(r.loan_id),"account_id":aid,"status":str(r.status),"target":label,"window":tag,"window_start":window_start.date().isoformat() if pd.notna(window_start) else "","window_end_exclusive":window_end.date().isoformat() if pd.notna(window_end) else "","calendar_months":den,"coverage_state":cw.coverage_state if cw else ("ALL_AVAILABLE_PRELOAN" if len(p) else "NO_PRELOAN_HISTORY"),"preloan_transaction_count":len(p),"eligible":eligible,"incomplete_coverage":not full_coverage if w else (not all_history_covered or not bool(len(p))),**{k:j(v) for k,v in vals.items()}})
    temporal_df=pd.DataFrame(temporal)
    pd.DataFrame(temporal_df).to_csv(OUT/"temporal_coverage.csv",index=False)
    rel["multiplicity"]["loans_without_preloan_transaction_history"] = int((temporal_df.preloan_transaction_count==0).sum())
    (OUT / "relational_integrity.json").write_text(json.dumps(rel, indent=2), encoding="utf-8")
    rec_df=pd.DataFrame(window_reconciliation)
    rec_df.to_csv(OUT/"window_reconciliation.csv",index=False)
    pd.DataFrame(monthly).to_csv(OUT/"monthly_histories.csv",index=False)
    f=pd.DataFrame(features); f.to_csv(OUT/"candidate_features_by_loan.csv",index=False)
    # Window feasibility for the matured A/B cohort.
    wr=[]
    matured_n=int(L.status.isin(["A","B"]).sum())
    for w in ["3m","6m","12m","all_preloan"]:
        s=f[(f.window==w)&f.status.isin(["A","B"])]; e=s[s.eligible]; nd=int((e.target==1).sum()); nn=int((e.target==0).sum())
        wr.append({"window":w,"eligible_loans":len(e),"default_cases":nd,"nondefault_cases":nn,"class_balance_default_pct":100*nd/len(e) if len(e) else np.nan,"median_transaction_count":e.preloan_transaction_count.median() if len(e) else np.nan,"minimum_transaction_count":int(e.preloan_transaction_count.min()) if len(e) else np.nan,"average_transaction_count":e.preloan_transaction_count.mean() if len(e) else np.nan,"accounts_with_incomplete_coverage":int(s.incomplete_coverage.sum()),"labeled_loans_retained_pct":100*len(e)/max(1,matured_n)})
    wdf=pd.DataFrame(wr); wdf.to_csv(OUT/"observation_window_analysis.csv",index=False)

    definitions={
    "avg_monthly_credit":"sum monthly PRIJEM transaction amounts / fixed calendar months",
    "avg_monthly_debit":"sum monthly VYDAJ and VYBER KARTOU transaction amounts / fixed calendar months",
    "credit_debit_ratio":"sum PRIJEM amounts / sum VYDAJ plus VYBER KARTOU amounts; missing if debit sum is zero",
    "avg_monthly_net_cashflow":"(sum PRIJEM - sum VYDAJ - sum VYBER KARTOU) / fixed calendar months",
    "cashflow_std":"sample SD (ddof=1) of monthly net cash flow; empty fixed-window months set to zero",
    "cashflow_cv":"cashflow_std / abs(mean monthly net cash flow); missing if mean is zero or fewer than two months",
    "positive_cashflow_month_ratio":"number of months with net flow > 0 / fixed months",
    "negative_cashflow_month_ratio":"number of months with net flow < 0 / fixed months",
    "negative_cashflow_month_count":"number of months with net flow < 0",
    "inflow_trend":"OLS slope of monthly PRIJEM total on chronological month index",
    "outflow_trend":"OLS slope of monthly VYDAJ plus VYBER KARTOU total on chronological month index",
    "avg_balance":"mean observed post-transaction balance in the window",
    "min_balance":"minimum observed post-transaction balance in the window",
    "max_balance":"maximum observed post-transaction balance in the window",
    "balance_std":"sample SD of observed post-transaction balances",
    "balance_cv":"sample SD / abs(mean) of observed balances; missing if mean zero or <2 observations",
    "low_balance_frequency":"share of observed balances <= 0 (analytical threshold only)",
    "negative_balance_frequency":"share of observed balances < 0",
    "end_of_month_balance_trend":"OLS slope of each represented month’s last observed balance on chronological month index",
    "documented_pension_credit_total":"sum of PRIJEM amounts with k_symbol DUCHOD; pension proxy, not salary",
    "pension_credit_month_ratio":"months containing DUCHOD PRIJEM / fixed calendar months; pension recurrence proxy, not salary regularity",
    "pension_credit_cv":"sample SD of monthly DUCHOD PRIJEM totals / absolute mean monthly pension credits; missing when mean is zero",
    "documented_loan_payment_total":"sum of pre-loan transaction amounts with k_symbol UVER",
    "documented_insurance_payment_total":"sum with k_symbol POJISTNE; insurance, not utility",
    "documented_household_payment_total":"sum with k_symbol SIPO; household payment marker, not utility",
    "permanent_order_total_amount":"NOT A PREDICTOR: order rows have no order date, so pre-loan availability cannot be established and the value risks post-loan leakage"}
    directions={"avg_monthly_credit":"ambiguous/context dependent","avg_monthly_debit":"ambiguous","credit_debit_ratio":"higher may mean lower risk; non-monotonic possible","avg_monthly_net_cashflow":"higher may mean lower risk","cashflow_std":"higher may mean volatility/risk","cashflow_cv":"higher may mean volatility/risk","positive_cashflow_month_ratio":"higher may mean lower risk","negative_cashflow_month_ratio":"higher may mean higher risk","negative_cashflow_month_count":"higher may mean higher risk","inflow_trend":"declining may mean higher risk","outflow_trend":"rising may mean higher risk","avg_balance":"higher may mean lower risk","min_balance":"lower may mean higher risk","max_balance":"ambiguous","balance_std":"higher may mean volatility","balance_cv":"higher may mean volatility","low_balance_frequency":"higher may mean higher risk","negative_balance_frequency":"higher may mean higher risk","end_of_month_balance_trend":"declining may mean higher risk","documented_pension_credit_total":"not salary; pension amount/regularity may proxy stable inflow","pension_credit_month_ratio":"higher recurrence may indicate stable pension income but not general salary","pension_credit_cv":"higher may indicate irregular pension amount; pension-only proxy","documented_loan_payment_total":"higher obligation amount may mean higher burden","documented_insurance_payment_total":"not utility; burden only","documented_household_payment_total":"not utility; burden only","permanent_order_total_amount":"not usable; undated source creates unresolved pre/post loan leakage"}
    rec={k:k not in ["documented_pension_credit_total","pension_credit_month_ratio","pension_credit_cv","documented_loan_payment_total","documented_insurance_payment_total","documented_household_payment_total","permanent_order_total_amount"] for k in definitions}
    dictionary=[]
    for k,v in definitions.items():
        src="trans.date, trans.account_id, trans.type, trans.amount" + (", trans.balance" if "balance" in k else "")
        if k.startswith("documented_") or k.startswith("pension_credit_"): src="trans.date, trans.account_id, trans.type, trans.amount, trans.k_symbol"
        if k=="permanent_order_total_amount": src="order.account_id, order.amount"
        dictionary.append({"feature":k,"definition":v,"source_fields":src,"observation_window":"fixed N complete calendar months before loan month (N=3 or 6 in this audit; origination month excluded)","missing_month_handling":"zero flows/counts only for an eligible, fully covered window; observed balances are not imputed; pre-account/source periods make window ineligible","zero_denominator":"ratio/CV missing when denominator is zero","valid_zero_semantics":"zero is a valid measured amount/count/share where observed; missing ratio/CV is distinct","expected_range":"unbounded monetary values; ratios/CV nonnegative or possibly signed only for slopes; shares [0,1]","transformation":"consider log1p for nonnegative amount features and robust scaling only inside future training folds","expected_risk_direction":directions[k],"statement_reproducible":"yes for typed cashflow/balance measures" if rec[k] else "not faithfully equivalent without category mapping or cadence evidence","lineage":"Berka trans rows -> shared complete-calendar window -> monthly aggregation -> formula; future parsed bank statement rows -> same shared window and typed monthly aggregation -> formula" if rec[k] else "typed Berka categories/orders -> proxy; future statement equivalence requires validation","notes":"Do not infer salary from generic credit; DUCHOD is documented pension. Fixed-window data satisfy transaction_date < loan_date and end before origination month."})
    pd.DataFrame(dictionary).to_csv(OUT/"candidate_feature_dictionary.csv",index=False)

    cols=[c for c in definitions if c in f and pd.to_numeric(f[c],errors="coerce").notna().any()]
    quality=[]; corr_blocks=[]; pairs=[]; classq=[]
    for w in ("3m","6m"):
        base=f[(f.window==w)&f.status.isin(["A","B"])&f.eligible].copy()
        for c in cols:
            v=pd.to_numeric(base[c],errors="coerce").replace([np.inf,-np.inf],np.nan)
            quality.append({"window":w,"feature":c,"count":int(v.notna().sum()),"missing_pct":100*v.isna().mean(),"mean":v.mean(),"std":v.std(),"min":v.min(),"q1":v.quantile(.25),"median":v.median(),"q3":v.quantile(.75),"max":v.max(),"zero_frequency_pct":100*(v==0).mean(),"extreme_value_frequency_pct":100*(v.abs()>v.abs().quantile(.99)).mean() if v.notna().any() else np.nan,"skewness":v.skew()})
        corr=base[cols].apply(pd.to_numeric,errors="coerce").corr(method="spearman")
        corr_out=corr.copy(); corr_out.insert(0,"window",w); corr_out.insert(1,"feature",corr_out.index); corr_blocks.append(corr_out.reset_index(drop=True))
        for i,a in enumerate(corr.columns):
            for b in corr.columns[i+1:]:
                val=corr.loc[a,b]
                if pd.notna(val): pairs.append({"window":w,"feature_a":a,"feature_b":b,"spearman_rho":val,"absolute_rho":abs(val),"strong_redundancy_flag":bool(abs(val)>=.8)})
        for cl,g in base.groupby("target"):
            for c in cols:
                v=pd.to_numeric(g[c],errors="coerce"); classq.append({"window":w,"target":int(cl),"label":"default B" if cl==1 else "successful A","feature":c,"count":int(v.notna().sum()),"mean":v.mean(),"median":v.median(),"std":v.std()})
    pd.DataFrame(quality).to_csv(OUT/"feature_quality.csv",index=False)
    pd.concat(corr_blocks,ignore_index=True).to_csv(OUT/"feature_correlation.csv",index=False)
    pd.DataFrame(pairs).sort_values(["window","absolute_rho"],ascending=[True,False]).to_csv(OUT/"feature_redundancy.csv",index=False)
    strong=[p for p in pairs if p["window"]=="6m" and abs(p["spearman_rho"])>=.8]
    redundancy_summary="; ".join(f'{p["feature_a"]}/{p["feature_b"]} rho={p["spearman_rho"]:.2f}' for p in sorted(strong,key=lambda z:abs(z["spearman_rho"]),reverse=True)[:8]) or "no pairs exceeded |rho| 0.8"
    pd.DataFrame(classq).to_csv(OUT/"feature_quality_by_target.csv",index=False)

    compat=[
    {"feature":"credit_debit_ratio","current_prism_definition":"BankFeatureEngineer: sum amount where type=CR divided by sum where type=DR over full uploaded statement; missing if debit total zero","berka_fields":"trans.type, trans.amount, trans.date","reproducible":"REPRODUCIBLE WITH REVISED DEFINITION","leakage_risk":"low only with strict pre-loan cutoff","statement_reproducible":"yes if parsed debit/credit types are reliable","recommendation":"Berka candidate uses PRIJEM / (VYDAJ + VYBER KARTOU); freeze revised semantics and window."},
    {"feature":"cashflow_cv","current_prism_definition":"BankFeatureEngineer: monthly sum of signed amount; sample SD divided by signed mean over represented months; missing if <2 months or mean zero","berka_fields":"trans.type, trans.amount, trans.date","reproducible":"REPRODUCIBLE WITH REVISED DEFINITION","leakage_risk":"low only with strict cutoff","statement_reproducible":"yes for monthly typed flows","recommendation":"Berka candidate includes empty covered calendar months and divides by absolute mean; deliberately revised."},
    {"feature":"net_to_gross_ratio","current_prism_definition":"SalaryFeatureEngineer: net_salary / gross_salary; missing if either unavailable or gross <= 0","berka_fields":"no gross/net salary fields; generic credits are not payroll","reproducible":"NOT SUPPORTED BY BERKA","leakage_risk":"salary transaction misclassification risk","statement_reproducible":"Berka cannot reproduce payslip ratio","recommendation":"Do not approximate from credits/debits; reassess only with salary-document evidence."},
    {"feature":"utility_stability","current_prism_definition":"UtilityFeatureEngineer combines available bill amount CV, missed-payment mean, and/or payment-date regularity; clipped 0–1","berka_fields":"SIPO=household marker, POJISTNE=insurance; no verified utility entity","reproducible":"NOT SUPPORTED BY BERKA","leakage_risk":"semantic mislabel risk","statement_reproducible":"requires verified utility category/counterparty","recommendation":"Exclude; neither SIPO nor POJISTNE means utility."},
    {"feature":"min_balance","current_prism_definition":"BankFeatureEngineer minimum closing_balance within 3 months before latest statement date","berka_fields":"trans.balance, trans.date","reproducible":"REPRODUCIBLE WITH REVISED DEFINITION","leakage_risk":"low with cutoff","statement_reproducible":"yes when statements contain running balances","recommendation":"Candidate uses minimum observed balance within fixed pre-loan window; revise time anchor/window."}]
    pd.DataFrame(compat).to_csv(OUT/"prism_feature_compatibility.csv",index=False)
    strict=L[L.status.isin(["A","B"])]; defaults=int((strict.status=="B").sum()); nondefaults=int((strict.status=="A").sum()); six=wdf[wdf.window=="6m"].iloc[0]
    old_cohorts=[]; removed_summary=[]
    for w in (3,6):
        tag=f"{w}m"; rr=rec_df[rec_df.window==tag]; old=rr[rr.old_rolling_eligible]; new=rr[rr.new_calendar_eligible]; removed=rr[rr.reconciliation_status=="SUPERSEDED_WINDOW_DEFINITION"]
        old_cohorts.append({"window":tag,"old_n":int(len(old)),"old_defaults":int(old.target.sum()),"old_nondefaults":int((old.target==0).sum()),"new_n":int(len(new)),"new_defaults":int(new.target.sum()),"new_nondefaults":int((new.target==0).sum()),"removed_loan_ids":removed.loan_id.astype(int).tolist()})
        open_dates=temporal_df.set_index("loan_id").account_open_date.to_dict()
        removed_summary.append(f'{tag}: '+(', '.join(f'{int(x.loan_id)} (opened {open_dates.get(int(x.loan_id))}, after {x.new_calendar_start})' for x in removed.itertuples()) or 'none'))
    window_summary="; ".join(f'{r.window}: N={int(r.eligible_loans)} ({int(r.default_cases)} B/{int(r.nondefault_cases)} A), retained={r.labeled_loans_retained_pct:.1f}%, incomplete labels={int(r.accounts_with_incomplete_coverage)}, txn median/min/mean={r.median_transaction_count}/{int(r.minimum_transaction_count)}/{r.average_transaction_count:.1f}' for r in wdf.itertuples())
    report=f'''# Phase 2A Berka audit and PRISM feature feasibility

## Scope and safety
No model, bins, WoE, calibrated probabilities, scores, or tiers were created. No active production files were intentionally edited. Raw `.asc` files were read only. All outputs are isolated under `backend/phase2/outputs/berka_audit/`.

## A. Dataset integrity
Files present: {', '.join(present)}. Raw table counts: {', '.join(f'{k}={len(v):,}' for k,v in t.items())}. See `dataset_audit.json` for each table’s columns, inferred types, missingness, categorical values, ranges, duplicate records and key duplicates. See `relational_integrity.json` for orphan and multiplicity checks. The bundled guide states its expected counts; compare them with these actual counts rather than assuming the guide is the loaded data.

## B. Loan target
The local PKDD guide defines A as contract finished with no problems; B as finished, loan not paid; C as running and OK so far; D as running with client in debt. Defensible strict matured target: A=0, B=1; exclude C and D because final outcomes are unresolved. Included N={len(strict):,}, B defaults={defaults:,}, A successful={nondefaults:,}, default rate={100*defaults/max(1,len(strict)):.2f}%. D is delinquent while running but is not equivalent to a matured unsuccessful outcome. `loan_target_analysis.csv` includes per-status counts, percentages, documented semantics, amount, duration, payment and grant-date summary.

## C. Temporal coverage and leakage
Loan outcome joins to history through `loan.account_id -> account.account_id -> trans.account_id`; where a client identity is needed, use the OWNER disposition: `loan.account_id -> disp.account_id -> disp.client_id -> client.client_id` with `disp.type=OWNER` (only an owner can request a loan under the guide). All predictive history is strictly `trans.date < loan.date`; same-day and later transactions are excluded. The guide labels k_symbol UVER as loan payment; post-grant UVER events are excluded and counted separately. Per-loan first/last pre-loan dates, history length, pre/post counts are in `temporal_coverage.csv`; monthly history rows contain pre-grant activity only. Permanent orders have no date and cannot be proven available pre-loan, so they are not predictors.

## D. Observation windows — corrected definition
Canonical window function: `first_day(loan_month) - N calendar months <= transaction_date < first_day(loan_month)`. The origination month is excluded. Account opening and dataset source coverage must span the entire interval; pre-account and uncovered periods are missing coverage, never zero-filled. The superseded Phase 2A implementation used `loan_date - DateOffset(months=N) <= transaction_date < loan_date`, a rolling date-offset window inconsistent with the earlier prose. Prior cohorts/statistics are archived and marked `SUPERSEDED_WINDOW_DEFINITION`; do not use them for modelling.

Regenerated all/3/6/12-month results (eligible N, defaults/nondefaults, retained labels, incomplete labels, transaction median/minimum/mean): {window_summary}. Reconciliation against the superseded cohorts: {old_cohorts}. Removed loans and account-open dates: {removed_summary}. Reconciliation detail is in `window_reconciliation.csv`. The corrected 3M and 6M counts are calculated from raw dates and the centralized tested utility, not hardcoded. The corrected window tables and statistics below are the sole Phase 2A source of truth.

## E. Candidate Feature Schema v2
The mathematical dictionary, window, missing-month/denominator semantics, zero semantics, expected ranges, transformations, direction, statement reproducibility, and lineage are in `candidate_feature_dictionary.csv`. Feature quality and correlations are regenerated separately for corrected 3M and 6M eligible cohorts. Bank transaction features use PRIJEM as credit and VYDAJ plus VYBER KARTOU as debit; other codes are not forced into either. Monthly exports include both corrected 3M and 6M fully covered cohorts, type counts and k_symbol amount totals. Empty months are zero for flow/count features only after complete-window eligibility; balances remain missing for months with no transactions. A month before account opening or source coverage is incomplete, not zero. Ratios are missing when the denominator is zero; valid observed zeros remain zeros. Pension: DUCHOD is documented as old-age pension, not salary. Generic credits are not salary. UVER, POJISTNE and SIPO may be preserved as typed category proxies, but none is called utility. Permanent orders have no date and cannot be leakage-safe pre-loan inputs.

## F. Current PRISM compatibility
See `prism_feature_compatibility.csv`, which was checked against the current feature engineer code. Credit/debit ratio and cashflow CV are reproducible only with revised explicit definitions; current credit/debit ratio is CR/DR across the statement, while the Berka candidate includes VYBER KARTOU withdrawals. Current cashflow CV uses represented statement months and a signed mean, while the candidate is fixed-window and divides by absolute mean. Current min_balance is 3 months before the latest statement date; Berka candidates anchor to the loan date. `net_to_gross_ratio` is payslip net/gross and unsupported by Berka. `utility_stability` uses bill amount, missed payments, and/or payment-date regularity and is unsupported by Berka. Do not map household SIPO or insurance to utility.

## Correlation and redundancy
Corrected-cohort Spearman |rho| >= 0.8 pairs on the eligible 6-month cohort include: {redundancy_summary}. The separate rows for 3M and 6M are in `feature_correlation.csv`; pair summaries are in `feature_redundancy.csv`. Use only as exploratory redundancy awareness, not final feature selection.

## G. Sample size and imbalance
For the strict matured target N={len(strict)}, defaults={defaults}, nondefaults={nondefaults}, default rate={100*defaults/max(1,len(strict)):.2f}%. For the eligible six-month cohort, events per hypothetical feature count: 5={six.default_cases/5:.2f}, 8={six.default_cases/8:.2f}, 10={six.default_cases/10:.2f}, 15={six.default_cases/15:.2f}. This is a few hundred loans, not over a million independent transaction examples. The low event counts make all those model sizes risky: five is weakly supported, and 8–15 are not reasonable for an ordinary unpenalized scorecard. A 1–2 effective-predictor initial candidate is more defensible; assess sample expansion, penalization and uncertainty in Phase 2B. No resampling or weighting was performed. Preserve natural prevalence for meaningful PD calibration.

## H. Limitations
One Czech bank, 1990s economy, historical currency and transaction coding limit transportability to current PRISM applicants. The ledger is not a modern uploaded PDF statement. Accounts can have multiple dispositions/owners; the target is account-level. Histories can be left-censored; assuming quiet calendar months have zero activity is defensible only where ledger coverage spans that month. Salary, modern utilities, and several PRISM document concepts are absent. PRISM-statement equivalence is plausible for typed flows/balances but requires parser/category validation.

## I. Phase 1 regression
The existing backend suite passes: 58 passed, 0 failed, 10 subtests passed. The active manifest still says `UNVERIFIED_REAL_WORLD` and `VERIFIED`; the model and binning files match the hashes recorded in the manifest. The suite includes actual `/assess` endpoint cases. No Phase 1 or frontend file was intentionally changed by this Phase 2A correction; the working tree already had unrelated modified and untracked files before this audit.

## J. Phase 2B readiness
Phase 2B remains **not started**. The corrected tested calendar-window helper and regenerated outputs are now the sole source of truth. Future feature generation and Phase 2B splits must call `phase2.windowing.complete_calendar_window`; do not use superseded rolling-window cohort/statistics. The small corrected event counts further constrain complexity: 31/5=6.2 events per feature for 3M and 19/5=3.8 for 6M; 1–2 effective predictors remain the conservative ceiling. Model training requires a separate task.

## Architecture answer
**Conditionally yes:** a Berka-trained behavioral candidate can use PRISM’s existing document-ingestion architecture if statement parsing can reproduce the same typed monthly transaction and observed-balance aggregates. The evidence favors bank statements alone for an initial candidate. Salary and utility documents are not faithfully supported by Berka. Equivalence to current statements is approximate and needs independent coverage/category validation.
'''
    (OUT/"phase2a_report.md").write_text(report,encoding="utf-8")
    (OUT/"raw_file_sha256.json").write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.iterdir() if p.is_file()},indent=2),encoding="utf-8")
    config_old={x["window"]:x for x in old_cohorts}
    summary={"phase":"2A_CORRECTED","model_training_performed":False,"status":"PHASE_2A_WINDOW_DEFINITION_CORRECTED","target":{"included_statuses":{"A":0,"B":1},"excluded_statuses":["C","D"]},"window_definition":{"status":"CANONICAL_COMPLETE_CALENDAR_MONTHS","formula":"first_day(loan_month)-N calendar months <= transaction_date < first_day(loan_month)","origination_month_excluded":True,"eligibility":"account_open_date <= window_start; source coverage spans [window_start, window_end_exclusive)","implementation":"phase2.windowing.complete_calendar_window"},"superseded_definition":{"status":"SUPERSEDED_WINDOW_DEFINITION","formula":"loan_date-DateOffset(months=N) <= transaction_date < loan_date","archived_directory":"superseded_rolling_window"},"cohorts":{r["window"]:{"eligible_n":int(r["eligible_loans"]),"defaults":int(r["default_cases"]),"nondefaults":int(r["nondefault_cases"]),"default_rate":float(r["class_balance_default_pct"])/100,"incomplete_label_count":int(r["accounts_with_incomplete_coverage"]),"retained_pct":float(r["labeled_loans_retained_pct"])} for r in wr},"superseded_cohorts":config_old,"removed_loans":[{"window":r["window"],"loan_id":int(r["loan_id"]),"account_id":int(r["account_id"]),"status":r["status"],"reason":r["new_coverage_state"],"account_open_date":next(x["account_open_date"] for x in temporal if x["loan_id"]==r["loan_id"])} for r in window_reconciliation if r["reconciliation_status"]=="SUPERSEDED_WINDOW_DEFINITION"],"phase2b_started":False,"phase1":{"model_validation_status":"UNVERIFIED_REAL_WORLD","runtime_status":"VERIFIED"}}
    (OUT/"phase2a_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
    archive=OUT/"superseded_rolling_window"
    archive.mkdir(exist_ok=True)
    archive_note=f'''# Superseded Phase 2A rolling-window snapshot\n\nStatus: `SUPERSEDED_WINDOW_DEFINITION`. These are preserved for audit trail only and must not be used for Phase 2B.\n\nThe prior implementation used `loan_date - DateOffset(months=N) <= transaction_date < loan_date`, although the report described complete calendar months. The canonical definition is now `first_day(loan_month) - N calendar months <= transaction_date < first_day(loan_month)`.\n\nOld cohorts: {json.dumps(config_old,sort_keys=True)}\nNew cohorts: {json.dumps({r["window"]:{"n":int(r["eligible_loans"]),"defaults":int(r["default_cases"]),"nondefaults":int(r["nondefault_cases"])} for r in wr},sort_keys=True)}\n\nThe original script and affected output files in this directory are unchanged snapshots from before correction.\n'''
    (archive/"README.md").write_text(archive_note,encoding="utf-8")
    print(json.dumps({"files":present,"counts":{k:len(v) for k,v in t.items()},"windows":wr,"status_counts":rel["status_counts"],"orphans":rel["orphan_checks"],"output":str(OUT)},indent=2,default=str))

if __name__ == "__main__": main()
