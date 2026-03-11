import subprocess
from fastapi.responses import FileResponse
from fastapi import UploadFile, File, Form
from google import genai
from google.genai import types
import docx
import re
import logging
from dotenv import load_dotenv
import io
import os
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
import re
import json


app = FastAPI()
load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INCLUDE_DIR = os.path.join(BASE_DIR, "include")
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
TEMP_JSON_PATH = os.path.join(INCLUDE_DIR, "paper-temp.json")

os.makedirs(PROJECTS_DIR, exist_ok=True)

TEMPLATE_REQUIREMENTS = {
    "neurips": {
        "name": "NeurIPS",
        "required": ["abstract", "introduction", "title", "method", "experiments"],
        "recommended": ["related work", "results", "conclusion"],
    },
    "cvpr": {
        "name": "CVPR",
        "required": ["abstract", "introduction", "compute budget"],
        "recommended": ["related work", "method", "experiments", "results", "conclusion", "appendix"],
    },
}


class RephraseRequest(BaseModel):
    text: str
    style: str = "academic"

class CompileRequest(BaseModel):
    project_name: str
    content: Dict[str, Any]

class UpdateRequest(BaseModel):
    project_name: str
    content: Dict[str, Any]

class ReviewRequest(BaseModel):
    project_name: str
    content: Dict[str, Any]

class CreateProjectRequest(BaseModel):
    project_name: str
    paper_type: int

# Helper function to clean project names
def get_safe_path(project_name: str):
    safe_name = "".join([c for c in project_name if c.isalnum() or c in (" ", "-", "_")]).strip()
    project_path = os.path.join(PROJECTS_DIR, safe_name)
    json_file_path = os.path.join(project_path, f"{safe_name}.json")
    return safe_name, project_path, json_file_path

def clean_docx_text(file_bytes: bytes) -> str:
    """Reads a docx file and cleans the raw text using regex."""
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        full_text = [para.text for para in doc.paragraphs]
        raw_text = '\n'.join(full_text)

        # Regex to remove tags
        cleaned_text = re.sub(r'\\s*', '', raw_text)

        # Regex to clean up excessive newlines
        cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)

        return cleaned_text
    except Exception as e:
        raise ValueError(f"Failed to parse docx file: {str(e)}")



def extract_and_repair_json(raw: str) -> dict:
    """
    Progressively tries to extract valid JSON from a Gemini response.
    Raises ValueError if all strategies fail.
    """
    # 1. Strip markdown fences
    cleaned = re.sub(r'^```(?:json)?\s*', '', raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*```$', '', cleaned.strip())

    # 2. Direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Extract outermost { ... } block
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 4. json-repair fallback (pip install json-repair)
    try:
        from json_repair import repair_json
        repaired = repair_json(cleaned)
        return json.loads(repaired)
    except Exception:
        pass

    raise ValueError(
        f"Could not parse Gemini response as JSON.\n"
        f"First 300 chars:\n{raw[:300]}"
    )


# ── Prompt builder ─────────────────────────────────────────────────────────────

def build_system_prompt() -> str:
    lines = [
        "You are an expert research paper formatter and academic writing assistant.",
        "",
        "The user has provided:",
        "1. A Word document containing rough research content.",
        "2. paper-schema.json defining the conference rules and structure.",
        "3. paper-temp.json defining the exact JSON structure for the final paper.",
        "",
        "Your task is to convert the Word document content into a properly structured research paper JSON.",
        "",
        "CORE INSTRUCTIONS:",
        "1. Read the Word document carefully and understand the research content.",
        "2. Follow all rules in paper-schema.json.",
        "3. Output strictly follows the structure in paper-temp.json — do NOT add or remove fields.",
        "4. Populate every field with content from the Word document.",
        "5. If a required section is missing, generate a reasonable academic placeholder.",
        "6. Maintain formal academic tone throughout.",
        "7. Return ONLY valid, parseable JSON. No markdown. No code fences. No explanation. Raw JSON only.",
        "",
        "JSON STRING SAFETY (CRITICAL — violations cause parse failures):",
        "- Every value must be a properly escaped JSON string.",
        r'- Inside a JSON string, a literal double-quote character must be written as \" (backslash-quote).',
        r"- NEVER place a raw unescaped double-quote character inside a JSON string value.",
        r"- NEVER place a raw newline inside a string value. Use \n if needed.",
        r"- NEVER place a raw backslash inside a string value unless it is a valid JSON escape sequence.",
        "- No trailing commas after the last element of any array or object.",
        "- The entire output must be one JSON object: starts with { and ends with }.",
        "",
        "GREEK LETTERS & TYPST MATH (CRITICAL):",
        "- You are writing Typst math syntax, NOT LaTeX.",
        "- Greek letters and math symbols use NO backslash prefix in Typst.",
        "  WRONG (LaTeX): \\Delta  \\alpha  \\beta  \\mu",
        "  RIGHT (Typst): Delta    alpha    beta    mu",
        "- Wrap math expressions in dollar signs: $Delta$  $alpha$  $mu$",
        "- Every opening $ must have a matching closing $.",
        r'- Literal currency dollar signs (e.g. $50) must be escaped as \$ inside Typst math context.',
        "",
        "QUOTING PLAIN TEXT WORDS INSIDE TYPST MATH:",
        "- In Typst, plain English words or identifiers inside a math block must be wrapped in",
        '  double-quote characters so Typst treats them as text, not math symbols.',
        '  Example Typst:  $Delta "grlA"$   $P_"LEE1"$   $"NaCl"$',
        "",
        "- Because you are outputting JSON, every double-quote character that appears INSIDE",
        r'  a JSON string value must be escaped as \". This applies to the Typst quotes too.',
        "",
        "  HOW TO WRITE TYPST MATH IN JSON VALUES:",
        r'    Typst you want:   $Delta "grlA"$',
        r'    In JSON value:    $Delta \"grlA\"$',
        "",
        r'    Typst you want:   $"NaCl"$',
        r'    In JSON value:    $\"NaCl\"$',
        "",
        r'    Typst you want:   $P_"LEE1"-"lacZ"$',
        r'    In JSON value:    $P_\"LEE1\"-\"lacZ\"$',
        "",
        r'    Typst you want:   $P_"LEE1"^"99T"-"gfp"$',
        r'    In JSON value:    $P_\"LEE1\"^\"99T\"-\"gfp\"$',
        "",
        "  WRONG — these break the JSON parser:",
        '    $Delta "grlA"$   ← raw unescaped quotes inside JSON string',
        "    $Delta grlA$     ← missing quotes, Typst will misrender",
        r"    $\Delta grlA$   ← LaTeX backslash, invalid in Typst",
        "",
        "  RULE SUMMARY: Every \" that would appear in the rendered Typst source",
        r'  must be written as \" in the raw JSON output.',
        "",
        "GENE / ACRONYM QUOTING IN PROSE (outside math):",
        '- Wrap gene names, acronyms, and species names in double-quotes in the Typst prose.',
        r'- In JSON these must also be escaped as \". Example:',
        r'    JSON value: "\"LEE1\" is the first transcriptional unit within the \"LEE\" region."',
        "",
        "STRUCTURE:",
        "- Map section/subsection headings to the `title` field of section objects.",
        "- Do NOT output headings as paragraph text.",
        "- Discard document headers, footers, and page numbers.",
        "",
        "FINAL SELF-CHECK BEFORE OUTPUT:",
        r'1. Every literal double-quote character inside a JSON string value is written as \".',
        "2. All Typst math uses Typst syntax (no backslashes for Greek letters).",
        "3. All plain-text words inside $...$ blocks are wrapped in Typst double-quotes,",
        r'   which are themselves escaped as \" in the JSON.',
        "4. No trailing commas after the last item in any array or object.",
        "5. Output is a single raw JSON object. No markdown fences. No preamble.",
        "6. Apostrophes (') inside string values do NOT need escaping. Write ' directly.","",
        "MULTI-LETTER IDENTIFIERS IN TYPST MATH (chemical formulas, units, abbreviations):",
        "- In Typst math, any sequence of two or more letters that should render as plain text",
        "  (not as a math symbol or Greek letter) MUST be wrapped in double-quotes.",
        "- This includes chemical formulas, units, and abbreviations.",
        "  Examples:",
        r'    Typst you want:   $\"CO\"_2$',
        r'    In JSON value:    $\"CO\"_2$',
        "",
        r'    Typst you want:   $\"H\"_2\"O\"$',
        r'    In JSON value:    $\"H\"_2\"O\"$',
        "",
        r'    Typst you want:   $\"NO\"_x$',
        r'    In JSON value:    $\"NO\"_x$',
        "",
        r'    Typst you want:   $\"CH\"_4$',
        r'    In JSON value:    $\"CH\"_4$',
        "",
        "  WRONG — single letters do not need quoting (they are valid math atoms):",
        r'    $C O_2$   ← two separate single-letter atoms, renders with space, looks wrong',
        r'    $CO_2$    ← Typst reads CO as C times O (implicit multiplication), also wrong',
        "  RIGHT:",
        r'    $\"CO\"_2$  ← Typst renders CO as a text label subscripted by 2',
        "",
        "- Apply this rule to: CO2, H2O, NOx, CH4, SO2, O3, NH3, and any similar",
        "  multi-letter chemical or unit abbreviation appearing in math context.",
    ]
    return "\n".join(lines)


def build_repair_prompt(bad_json: str, error_msg: str) -> str:
    lines = [
        f"Your previous response contained invalid JSON. Parse error: {error_msg}",
        "",
        "Fix ALL issues and return ONLY the corrected valid JSON object.",
        "Rules:",
        r'- Every literal double-quote character inside a JSON string value must be written as \".',
        r'- Typst math uses NO backslashes for Greek letters: write Delta not \Delta.',
        r'- Plain text words inside Typst $...$ blocks must be quoted with \"-escaped quotes.',
        r'  Example correct JSON value: "The $Delta \"grlA\"$ mutant showed reduced expression."',
        "- Remove all trailing commas after the last array/object element.",
        "- No markdown fences, no explanation. Raw JSON only.",
        "",
        f"Your broken response (first 2000 chars):\n{bad_json[:2000]}",
    ]
    return "\n".join(lines)

@app.post("/create-project")
async def create_project(request: CreateProjectRequest):
    if request.paper_type not in [1, 2]:
        raise HTTPException(status_code=400, detail="paper_type must be 1 or 2")

    safe_name, project_path, new_json_path = get_safe_path(request.project_name)

    if not os.path.exists(TEMP_JSON_PATH):
        raise HTTPException(status_code=500, detail="paper-temp.json not found")

    try:
        os.makedirs(project_path, exist_ok=True)
        with open(TEMP_JSON_PATH, "r", encoding="utf-8") as f:
            template_content = json.load(f)

        with open(new_json_path, "w", encoding="utf-8") as f:
            json.dump(template_content, f, indent=4)

        meta_file_path = os.path.join(project_path, "meta.json")
        meta_data = {
            "project_name": safe_name,
            "paper_type": "single-column" if request.paper_type == 1 else "double-column",
            "template_file": "single-column.typ" if request.paper_type == 1 else "double-column.typ"
        }
        with open(meta_file_path, "w", encoding="utf-8") as f:
            json.dump(meta_data, f, indent=4)

        return {"status": "success", "content": template_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/update-project")
async def update_project(request: UpdateRequest):
    _, _, json_file_path = get_safe_path(request.project_name)

    if not os.path.exists(json_file_path):
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(request.content, f, indent=4)
        return {"status": "success", "message": "Updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get-project/{project_name}")
async def get_project(project_name: str):
    """
    Retrieves the JSON content for a specific project.
    Usage: GET /get-project/MyProjectName
    """
    safe_name, _, json_file_path = get_safe_path(project_name)

    if not os.path.exists(json_file_path):
        raise HTTPException(
            status_code=404,
            detail=f"Project '{safe_name}' not found or JSON file is missing."
        )

    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            content = json.load(f)

        return {
            "project_name": safe_name,
            "content": content
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")




@app.post("/convert-paper")
async def convert_paper(
        project_name: str = Form(...),
        project_type: int = Form(...),
        file: UploadFile = File(...)
):
    if project_type not in [1, 2]:
        raise HTTPException(status_code=400, detail="project_type must be 1 (single-column) or 2 (double-column)")

    if not file.filename.endswith('.docx'):
        raise HTTPException(status_code=400, detail="Only .docx files are supported.")

    # 1. Read and clean the docx
    try:
        file_bytes = await file.read()
        cleaned_text = clean_docx_text(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 2. Read local JSON files
    try:
        with open(os.path.join(INCLUDE_DIR, "paper-schema.json"), "r", encoding="utf-8") as f:
            schema_content = f.read()
        with open(os.path.join(INCLUDE_DIR, "paper-temp.json"), "r", encoding="utf-8") as f:
            sample_content = f.read()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Required include file not found: {str(e)}")

    # 3. Build prompts
    system_instruction = build_system_prompt()

    user_prompt = (
        f"--- DOCX CONTENT ---\n{cleaned_text}\n\n"
        f"--- PAPER-SCHEMA.JSON ---\n{schema_content}\n\n"
        f"--- PAPER-TEMP.JSON ---\n{sample_content}\n\n"
        f"Project Name: {project_name}\n"
        f"Project Type: {'single-column' if project_type == 1 else 'double-column'}\n"
    )

    # 4. Call Gemini with retry
    MAX_RETRIES = 2
    raw = ""
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            contents = user_prompt if attempt == 0 else build_repair_prompt(raw, str(last_error))

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    temperature=0.1,
                )
            )

            raw = response.text.strip() if response.text else ""
            result_json = extract_and_repair_json(raw)

            # ── Success: save files ──
            safe_name, project_path, json_file_path = get_safe_path(project_name)
            os.makedirs(project_path, exist_ok=True)

            with open(json_file_path, "w", encoding="utf-8") as f:
                json.dump(result_json, f, indent=4, ensure_ascii=False)

            meta_file_path = os.path.join(project_path, "meta.json")
            meta_data = {
                "project_name": safe_name,
                "paper_type": "single-column" if project_type == 1 else "double-column",
                "template_file": "single-column.typ" if project_type == 1 else "double-column.typ"
            }
            with open(meta_file_path, "w", encoding="utf-8") as f:
                json.dump(meta_data, f, indent=4)

            return result_json

        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                continue
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Gemini returned invalid JSON after {MAX_RETRIES + 1} attempts: {str(last_error)} "
                    f"| Raw (first 500 chars): {raw[:500]}"
                )
            )

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Gemini API error or file save error: {str(e)}"
            )

@app.post("/compile")
async def compile_project(request: CompileRequest):
    safe_name, project_path, json_file_path = get_safe_path(request.project_name)

    # 1. Ensure the project exists
    if not os.path.exists(project_path):
        raise HTTPException(status_code=404, detail=f"Project '{safe_name}' not found.")

    # 2. Update the JSON file with the incoming content
    try:
        with open(json_file_path, "w", encoding="utf-8") as f:
            json.dump(request.content, f, indent=4)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update JSON: {str(e)}")

    # 3. Read meta.json to determine the template type
    meta_file_path = os.path.join(project_path, "meta.json")
    if not os.path.exists(meta_file_path):
        raise HTTPException(status_code=500, detail="meta.json is missing. Cannot determine paper type.")

    try:
        with open(meta_file_path, "r", encoding="utf-8") as f:
            meta_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading meta.json: {str(e)}")

    template_file = meta_data.get("template_file")
    if not template_file:
        raise HTTPException(status_code=500, detail="template_file not specified in meta.json")

    # 4. Construct Absolute and Root-Relative Paths
    typst_exe = os.path.join(INCLUDE_DIR, "typst.exe")
    input_template_path = os.path.join(INCLUDE_DIR, template_file)
    absolute_pdf_path = os.path.join(project_path, f"{safe_name}.pdf")

    # By starting this path with "/", Typst knows to look relative to the --root folder
    # This completely bypasses the template file's location.
    input_json_path = f"/projects/{safe_name}/{safe_name}.json"

    # The exact command
    command = [
        typst_exe,
        "compile",
        "--root", BASE_DIR,  # Explicitly set the Typst root to your absolute server directory
        "--input", f"json_path={input_json_path}",
        input_template_path,
        absolute_pdf_path
    ]

    # 5. Execute the Typst compiler
    try:
        process = subprocess.run(
            command,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            check=False
        )

        if process.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Typst compilation failed:\n{process.stderr}"
            )

    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="typst.exe not found in the include directory.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing compiler: {str(e)}")

    # 6. Verify PDF creation and return it to the frontend
    if not os.path.exists(absolute_pdf_path):
        raise HTTPException(status_code=500, detail="Compilation succeeded but PDF file was not found.")

    return FileResponse(
        path=absolute_pdf_path,
        media_type="application/pdf",
        filename=f"{safe_name}.pdf"
    )


@app.post("/review")
async def review_paper(request: ReviewRequest):
    """
    Reviews a paper JSON against template requirements.
    - single-column projects → NeurIPS criteria
    - double-column projects → CVPR criteria
    Returns an AI-generated structured review with scores and recommendations.
    """
    # 1. Resolve project and read meta.json
    safe_name, project_path, _ = get_safe_path(request.project_name)

    meta_file_path = os.path.join(project_path, "meta.json")
    if not os.path.exists(meta_file_path):
        raise HTTPException(
            status_code=404,
            detail=f"Project '{safe_name}' not found or meta.json is missing."
        )

    try:
        with open(meta_file_path, "r", encoding="utf-8") as f:
            meta_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading meta.json: {str(e)}")

    # 2. Map paper_type → template key
    paper_type = meta_data.get("paper_type", "")
    if paper_type == "single-column":
        template_key = "neurips"
    elif paper_type == "double-column":
        template_key = "cvpr"
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown paper_type '{paper_type}' in meta.json. Expected 'single-column' or 'double-column'."
        )

    reqs = TEMPLATE_REQUIREMENTS[template_key]

    # 3. Extract text, section headers, and word count from the JSON content
    try:
        paper_text, section_headers, word_count = extract_paper_text_and_sections(request.content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse paper content: {str(e)}")

    title = request.content.get("title", "(untitled)")

    # 4. Build the all_sections list for the prompt (required + recommended, deduplicated)
    all_sections = list(dict.fromkeys(reqs["required"] + reqs["recommended"]))

    # 5. Build the review prompt
    prompt = f"""You are a senior academic reviewer for a {reqs['name']} paper submission.

Paper title: {title}
Template: {reqs['name']}
Word count (approx): {word_count}
Section headers found: {json.dumps(section_headers)}

REQUIRED sections for {reqs['name']}: {json.dumps(reqs['required'])}
RECOMMENDED sections: {json.dumps(reqs['recommended'])}

Paper content (first 5000 chars):
{paper_text[:5000]}

Evaluate the paper and return ONLY a valid JSON object (no markdown fences):
{{
  "section_check": {{
    "abstract": {{"present": true, "quality": "good", "note": "Well-structured abstract covering motivation and results."}},
    "introduction": {{"present": false, "quality": "missing", "note": "No introduction section found."}}
  }},
  "scores": {{
    "completeness": {{"score": 6, "comment": "Missing Limitations section which is required."}},
    "writing_quality": {{"score": 7, "comment": "Clear prose but some sections lack transitions."}},
    "technical_depth": {{"score": 5, "comment": "Experiments section needs more ablation studies."}},
    "structure": {{"score": 7, "comment": "Logical flow but Related Work comes too late."}}
  }},
  "recommendations": [
    "Add a Limitations section — this is mandatory for {reqs['name']} submissions.",
    "Include quantitative baselines in the Experiments section.",
    "Expand the Related Work with recent (2023–2024) citations."
  ],
  "overall_assessment": "The paper presents an interesting approach but is missing key required sections. With revisions it could meet {reqs['name']} standards."
}}

IMPORTANT:
- section_check must include ALL sections from: {json.dumps(all_sections)}
- quality values: "good" | "fair" | "needs_work" | "missing"
- scores are integers 1–10
- Be specific and actionable in comments and recommendations
- A section is "present" if the headers list contains a matching or similar term
"""

    # 6. Call Gemini and return structured result
    raw = ""
    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            )
        )
        raw = resp.text.strip() if resp.text else ""
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw)

        result = json.loads(raw)

        # Attach metadata to the response
        result["template_name"] = reqs["name"]
        result["required_sections"] = reqs["required"]
        result["recommended_sections"] = reqs["recommended"]
        result["word_count"] = word_count
        result["sections_found"] = section_headers

        return result

    except json.JSONDecodeError as e:
        logger.error("Review JSON parse error: %s | raw: %.300s", e, raw)
        raise HTTPException(status_code=500, detail=f"AI returned invalid JSON: {e}")
    except Exception as e:
        logger.error("Review error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rephrase")
async def rephrase_text(request: RephraseRequest):
    """
    Rephrase a selected passage using Gemini.
    Styles: academic | simpler | concise | elaborate | fluent
    """
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="No text provided.")

    style_map = {
        "academic":  "Rephrase the following text in a formal, academic style suitable for a research paper. Improve clarity and precision.",
        "simpler":   "Simplify the following text. Use plain language and shorter sentences while preserving the core meaning.",
        "concise":   "Make the following text more concise. Remove redundancy and tighten the writing without losing meaning.",
        "elaborate": "Expand and elaborate on the following text. Add nuance, detail, and academic depth while staying on topic.",
        "fluent":    "Improve the fluency and flow of the following text. Fix awkward phrasing while preserving the original meaning.",
    }
    instruction = style_map.get(request.style, style_map["academic"])

    prompt = (
        f"{instruction}\n\n"
        f"Return ONLY the rephrased text — no explanations, no quotation marks, no preamble.\n\n"
        f"Text: {request.text}"
    )

    try:
        resp = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.4)
        )
        rephrased = resp.text.strip().strip('"').strip("'")
        return {"rephrased": rephrased, "original": request.text, "style": request.style}
    except Exception as e:
        logger.error("Rephrase error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))