import streamlit as st
from groq import Groq
import json
import random
import csv
import urllib.request
import os
from neo4j import GraphDatabase

# Optional: Google Gen AI SDK for Commercial Control
try:
    from google import genai
    HAS_GEMINI_SDK = True
except ImportError:
    HAS_GEMINI_SDK = False

# --- CONFIGURATION ---
NEO4J_URI = "neo4j+s://321c130b.databases.neo4j.io"
NEO4J_PASSWORD = "ZqyErQjUfJIZBo6qcB80lui0QyLuMoOXCjmS521DbLA"
OLLAMA_ENDPOINT = "http://localhost:11434/api/chat"
LOCAL_MODEL = "llama3.2:1b"

def get_neo4j_driver():
    for user in ["321c130b", "neo4j"]:
        try:
            driver = GraphDatabase.driver(NEO4J_URI, auth=(user, NEO4J_PASSWORD))
            driver.verify_connectivity()
            return driver
        except Exception:
            continue
    return None

# --- CLINICAL BENCHMARK VIGNETTES ---
vignettes = [
    {
        "id": "V-001",
        "prompt": "Evaluate a 6-year-old pediatric oncology patient in Active Chemotherapy presenting for Surgical Extraction. Blood counts: ANC 600/mm³, Platelets 35,000/mm³. Detail safety considerations and action plan.",
        "anc": 600,
        "platelets": 35000,
        "phase": "Active Chemotherapy / Induction",
        "procedure": "Surgical Extraction"
    },
    {
        "id": "V-002",
        "prompt": "Evaluate an 11-year-old patient in Maintenance Phase presenting for Elective Restorative Care. Blood counts: ANC 2,200/mm³, Platelets 150,000/mm³. Detail safety considerations and action plan.",
        "anc": 2200,
        "platelets": 150000,
        "phase": "Maintenance Phase",
        "procedure": "Elective Restorative Care"
    },
    {
        "id": "V-003",
        "prompt": "Evaluate a 9-year-old patient in Consolidation Phase requiring Periodontal Scaling. Blood counts: ANC 1,200/mm³, Platelets 45,000/mm³. Detail safety considerations and action plan.",
        "anc": 1200,
        "platelets": 45000,
        "phase": "Consolidation Phase",
        "procedure": "Periodontal Scaling"
    },
    {
        "id": "V-004",
        "prompt": "Evaluate a 14-year-old patient 45 days Post-HSCT with irritating Orthodontic Appliances. Blood counts: ANC 800/mm³, Platelets 80,000/mm³. Detail safety considerations and action plan.",
        "anc": 800,
        "platelets": 80000,
        "phase": "Post-HSCT (First 100 Days)",
        "procedure": "Orthodontic Appliances"
    }
]


def call_commercial_llm(prompt):
    # This securely pulls the key you pasted into Streamlit Secrets
    client = Groq(api_key=st.secrets["GROQ_API_KEY"])
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama3-8b-8192", 
    )
    return response.choices[0].message.content
    def call_local_ollama(prompt):
        return call_commercial_llm(prompt)

def call_local_ollama(prompt):
    # This catches any accidental local calls and reroutes them to the cloud
    return call_commercial_llm(prompt)

def query_neo4j_rules(driver, procedure_name):
    query = """
    MATCH (source)-[r:CONTRAINDICATES]->(target:Intervention)
    WHERE ($proc IS NULL OR toLower(target.name) CONTAINS toLower($proc))
    RETURN source.name AS Condition, source.description AS Description, r.clinical_rule AS Rule
    """
    try:
        with driver.session() as session:
            return list(session.run(query, proc=procedure_name))
    except Exception:
        return []

# --- 2-ARM GENERATIONS ---

def generate_arm1_commercial(vignette):
    """ARM 1: Commercial Frontier LLM Control (No Graph RAG)"""
    prompt = f"You are an AI clinical decision support assistant for pediatric dental oncology. Respond formally into 3 sections (1. Patient Profile, 2. Guideline Assessment, 3. Management Plan):\n\n{vignette['prompt']}"
    return call_commercial_llm(prompt)

def generate_arm2_graphrag(driver, vignette):
    """ARM 2: P-DONG-RAG Experimental System (Local Llama + Neo4j Graph)"""
    records = query_neo4j_rules(driver, vignette['procedure'])
    violations = []
    for rec in records:
        cond = rec["Condition"].lower()
        if vignette['anc'] < 1000 and "anc < 1,000" in cond:
            violations.append(rec["Rule"])
        if vignette['platelets'] < 40000 and "platelets < 40,000" in cond:
            violations.append(rec["Rule"])
        if "active" in vignette['phase'].lower() and "active chemotherapy" in cond:
            violations.append(rec["Rule"])

    context_str = "Mandatory Enforced Rules: " + "; ".join(violations) if violations else "Cleared. No contraindications triggered."

    prompt = f"""
    You are an AI clinical decision support assistant for pediatric dental oncology grounded in AAPD/MASCC guidelines.

    [GROUND TRUTH GRAPH FACTS]
    {context_str}

    [CLINICAL QUERY]
    {vignette['prompt']}

    Draft a formal consultation note (1. Patient Profile, 2. Guideline Assessment, 3. Management Plan) strictly respecting the Ground Truth Graph Facts.
    """
    return call_local_ollama(prompt)

def main():
    driver = get_neo4j_driver()
    if not driver:
        print("❌ Could not connect to Neo4j database.")
        return

    print("🚀 Generating 2-Arm Comparative Study Dataset (Commercial LLM vs. P-DONG-RAG)...")

    eval_rows = []
    unblinding_key = {}

    for v in vignettes:
        print(f"🔄 Processing Vignette {v['id']}...")
        
        arm1_res = generate_arm1_commercial(v)
        arm2_res = generate_arm2_graphrag(driver, v)

        # Randomize Output A and Output B for double-blind review
        if random.choice([True, False]):
            out_a, out_b = arm2_res, arm1_res
            unblinding_key[v["id"]] = {"Output_A": "P-DONG-RAG (GraphRAG)", "Output_B": "Commercial LLM Control"}
        else:
            out_a, out_b = arm1_res, arm2_res
            unblinding_key[v["id"]] = {"Output_A": "Commercial LLM Control", "Output_B": "P-DONG-RAG (GraphRAG)"}

        eval_rows.append({
            "Vignette ID": v["id"],
            "Clinical Vignette Prompt": v["prompt"],
            "Output A": out_a,
            "Output B": out_b,
            "Rating Output A (1-5)": "",
            "Rating Output B (1-5)": "",
            "Safety Violation A (0/1)": "",
            "Safety Violation B (0/1)": "",
            "Preferred Output (A/B)": ""
        })

    # Save outputs
    with open("expert_evaluation_sheet_2arm.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=eval_rows[0].keys())
        writer.writeheader()
        writer.writerows(eval_rows)

    with open("unblinding_key_2arm.json", "w", encoding="utf-8") as f:
        json.dump(unblinding_key, f, indent=4)

    print("\n✅ 2-Arm Dataset Generation Complete!")
    print("1. Blinded Sheet for Evaluators: expert_evaluation_sheet_2arm.csv")
    print("2. Secret Unblinding Key: unblinding_key_2arm.json")

if __name__ == "__main__":
    main()
