def _payload(event_type="review_decision", **overrides):
    payload = {
        "tenant_id": "kone",
        "correlation_id": "api-run-1",
        "plan_fingerprint": "1" * 64,
        "evidence_snapshot_id": f"evidence:GUIDES-59991:{'2' * 64}",
        "event_type": event_type,
        "decision": "QE_APPROVED",
        "payload": {},
        "idempotency_key": f"api-{event_type}",
    }
    payload.update(overrides)
    return payload


def test_feedback_api_records_lists_and_summarizes(client, auth_headers):
    review = client.post(
        "/api/v1/test-plans/GUIDES-59991/feedback",
        headers=auth_headers,
        json=_payload(),
    )
    execution = client.post(
        "/api/v1/test-plans/GUIDES-59991/feedback",
        headers=auth_headers,
        json=_payload(
            "execution_outcome",
            decision="",
            outcome="PASS",
            ac_id="UAC-01",
            ac_fingerprint="3" * 64,
            payload={"environment": "cloud", "test_case_id": "TC-01"},
        ),
    )
    listed = client.get(
        "/api/v1/test-plans/GUIDES-59991/feedback?tenant_id=kone",
        headers=auth_headers,
    )
    summary = client.get(
        "/api/v1/test-plans/GUIDES-59991/quality-summary?tenant_id=kone",
        headers=auth_headers,
    )

    assert review.status_code == 200, review.text
    assert execution.status_code == 200, execution.text
    assert listed.status_code == 200
    assert listed.json()["count"] >= 2
    assert summary.status_code == 200
    assert summary.json()["review_decisions"]["QE_APPROVED"] >= 1
    assert summary.json()["execution_outcomes"]["PASS"] >= 1
    assert summary.json()["learning_policy"]["automatic_authority_promotion"] is False


def test_feedback_api_rejects_untraceable_execution(client, auth_headers):
    response = client.post(
        "/api/v1/test-plans/GUIDES-59992/feedback",
        headers=auth_headers,
        json={
            **_payload("execution_outcome"),
            "evidence_snapshot_id": f"evidence:GUIDES-59992:{'2' * 64}",
            "decision": "",
            "outcome": "PASS",
        },
    )

    assert response.status_code == 400
    assert "requires ac_id and ac_fingerprint" in response.json()["detail"]
