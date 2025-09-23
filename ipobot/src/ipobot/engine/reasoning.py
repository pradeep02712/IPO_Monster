
def build_reason(symbol, sent, fdetail, prob, gain_est, decision):
    pts = []
    if sent >= 0.3:
        pts.append(f"News sentiment positive ({sent:+.2f})")
    elif sent <= -0.3:
        pts.append(f"News sentiment negative ({sent:+.2f})")
    else:
        pts.append(f"News sentiment mixed ({sent:+.2f})")

    if fdetail.get("pe_discount_vs_peer") is not None:
        if fdetail["pe_discount_vs_peer"] > 0.1:
            pts.append("Valuation cheaper than peers (>10% discount)")
        elif fdetail["pe_discount_vs_peer"] < -0.05:
            pts.append("Valuation richer than peers (>5% premium)")

    if fdetail.get("roe_flag"):
        pts.append("ROE ≥ 15%")
    if fdetail.get("d2e_flag"):
        pts.append("Debt-to-Equity ≤ 1.0 (manageable leverage)")
    if fdetail.get("growth_flag"):
        pts.append("Revenue CAGR ≥ 20% (growth)")

    pts.append(f"Model gain probability {prob:.2f}, expected gain ≈ {gain_est:.1f}%")

    why = f"""**{decision}** for {symbol} because:
- """ + "\n- ".join(pts)
    return why
