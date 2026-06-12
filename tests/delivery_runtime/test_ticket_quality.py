"""Tests for Jira ticket quality detection."""

from __future__ import annotations

from delivery_runtime.pm_inbox.analyst import analyze_for_daily_delivery
from delivery_runtime.readiness.ticket_quality import (
    has_acceptance_criteria,
    has_actionable_specification,
    has_reproduction_steps,
    has_structured_bug_report,
)
from delivery_runtime.readiness.scoring import score_ticket

TVP_2233_DESCRIPTION = """
Test en prod WEB V3.4.5 : les 128 épisodes des Tortues Ninja n'apparaissent pas tous dans le rail épisode.

Étapes pour reproduire :
Étape 1 : Aller sur https://www.tv5mondeplus.com/fr/jeunesse/a-partir-de-9-ans/les-tortues-ninja
Étape 2 : Faire défiler le rail des épisodes jusqu'à la fin
Étape 3 : Observer la liste des épisodes affichés

Résultat attendu :
Les 128 épisodes sont présents indépendamment du niveau de zoom ou de la taille de l'écran.

Résultat observé :
L'épisode 128 est absent dans les conditions normales d'affichage.
"""


def test_french_bug_description_has_reproduction_and_acceptance_signals():
    assert has_reproduction_steps(TVP_2233_DESCRIPTION)
    assert has_structured_bug_report(TVP_2233_DESCRIPTION)
    assert has_acceptance_criteria(TVP_2233_DESCRIPTION, issue_type="bug")


def test_french_bug_ticket_scores_ready_with_repository():
    snapshot = {
        "key": "TVP-2233",
        "summary": "[BUG] Rail épisode incomplet - Série Les Tortues Ninja",
        "description": TVP_2233_DESCRIPTION,
        "status": "To Do",
        "issueType": "Bug",
        "projectKey": "TVP",
    }
    result = score_ticket(snapshot, recommended_repos=["gitlab.com/client/tv5plus"])
    assert result.status == "ready"
    assert not any("Acceptance criteria" in blocker for blocker in result.blockers)


TVP_1489_DESCRIPTION = """
Bonjour,

La grille du guide https://www.tv5mondeplus.com/fr/guide-tv n'est pas présente dans le code HTML
pour TV5MONDE+, cela veut dire qu'elle est générée côté client (via JavaScript ou un appel API)
après le chargement initial. Cela pose un problème pour Google lors du crawl qui ne voit pas le
contenu de la page. Il existe différentes solutions pour régler ce problème => Voir slides 2 et 3
du PPT en PJ.

Rendu de la page Guide (1).pdf

Si vous avez besoin de précisions, Florian de l'agence Wam peut se rendre dispo pour un call.

Merci
"""


def test_seo_story_with_url_and_impact_is_actionable_without_explicit_ac():
    summary = "[WEB] [SEO] Guide TV - Problème rendering"
    assert has_actionable_specification(
        TVP_1489_DESCRIPTION,
        issue_type="Story",
        summary=summary,
    )
    assert has_acceptance_criteria(
        TVP_1489_DESCRIPTION,
        issue_type="Story",
        summary=summary,
    )


def test_seo_story_without_repo_is_ready_not_needs_clarification(monkeypatch):
    monkeypatch.setattr(
        "delivery_runtime.pm_inbox.analyst.resolve_recommended_repos",
        lambda _project_key, _snapshot: [],
    )
    snapshot = {
        "key": "TVP-1489",
        "summary": "[WEB] [SEO] Guide TV - Problème rendering",
        "description": TVP_1489_DESCRIPTION,
        "status": "To Do",
        "issueType": "Story",
        "projectKey": "TVP",
    }
    analysis = analyze_for_daily_delivery(snapshot)
    assert analysis["readinessStatus"] == "ready"
    assert analysis["analystCategory"] == "needs_repo_mapping"
    assert analysis["proposalType"] != "needs_clarification"
    assert analysis["proposedComment"] == ""
    assert analysis["actionable"] is True
    assert any("repository" in issue.lower() for issue in analysis["detectedIssues"])


def test_french_bug_ticket_is_actionable_in_daily_analyst(monkeypatch):
    monkeypatch.setattr(
        "delivery_runtime.pm_inbox.analyst.resolve_recommended_repos",
        lambda _project_key, _snapshot: ["gitlab.com/client/tv5plus"],
    )
    snapshot = {
        "key": "TVP-2233",
        "summary": "[BUG] Rail épisode incomplet - Série Les Tortues Ninja",
        "description": TVP_2233_DESCRIPTION,
        "status": "To Do",
        "issueType": "Bug",
        "projectKey": "TVP",
    }
    analysis = analyze_for_daily_delivery(snapshot)
    assert analysis["readinessStatus"] == "ready"
    assert analysis["actionable"] is True
    assert analysis["analystCategory"] == "development_ready"
