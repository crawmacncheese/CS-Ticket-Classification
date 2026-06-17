"""Collapsed pipeline documentation for the local test portal."""

from __future__ import annotations

_PIPELINE_MERMAID = r"""flowchart TB
  subgraph inputs [Inputs]
    NDJSON[Zendesk NDJSON]
    WB[doc workbook]
    TC[Taxonomy.csv]
    RULES[classifier_rules.json]
  end

  subgraph allow [Allow-list]
    LOAD[load_allowlist]
    WB --> LOAD
    TC --> LOAD
    LOAD --> ALLOW[(AllowList)]
  end

  subgraph row [Each ticket]
    FLAT[flatten_ticket]
    SIG[_signals]
    RULES_MATCH[rule matching]
    SCORE[score by 5-tuple]
    PICK[pick best]
    MASTER[MASTER_COLUMNS row]

    FLAT --> SIG
    SIG --> RULES_MATCH
    RULES_MATCH --> SCORE
    ALLOW -.-> SCORE
    SCORE --> PICK
    PICK --> MASTER
  end

  NDJSON --> FLAT
  MASTER --> UI[portal + CSV]
"""


def pipeline_docs_html() -> str:
    """Collapsed pipeline architecture diagram (README overview, compact)."""
    return f"""<section class="readme-doc" aria-label="Pipeline architecture">
    <details id="readme-pipeline-details" class="readme-details">
      <summary>Pipeline architecture</summary>
      <div class="readme-body readme-pipeline-diagram">
        <div class="mermaid">{_PIPELINE_MERMAID}</div>
      </div>
    </details>
    </section>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js" crossorigin="anonymous"></script>
    <script>
    (function () {{
      if (typeof mermaid === "undefined") return;
      mermaid.initialize({{
        startOnLoad: false,
        theme: "neutral",
        securityLevel: "loose",
        themeVariables: {{ fontSize: "11px" }},
        flowchart: {{ useMaxWidth: true, padding: 6, nodeSpacing: 28, rankSpacing: 24 }}
      }});
      var det = document.getElementById("readme-pipeline-details");
      if (!det) return;
      det.addEventListener("toggle", function () {{
        if (!det.open || det.getAttribute("data-mermaid-rendered")) return;
        det.setAttribute("data-mermaid-rendered", "1");
        var node = det.querySelector(".mermaid");
        if (!node) return;
        try {{
          mermaid.run({{ nodes: [node] }});
        }} catch (e) {{}}
      }});
    }})();
    </script>"""
