"""FastAPI PaddleOCR Inference Server for EC2

This server provides HTTP endpoints for OCR inference using PaddleOCR models.
Supports: PaddleOCR-VL, PP-OCRv5, PP-StructureV3

Models are loaded on demand and cached locally.
"""
import os
import tempfile
import logging
import time
from typing import Dict, Any, List

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from contextlib import asynccontextmanager
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MODEL_CACHE_BUCKET = os.environ.get("MODEL_CACHE_BUCKET", "")
PADDLEOCR_HOME = os.environ.get("PADDLEOCR_HOME", "/opt/paddleocr/models/.paddleocr")
PADDLEX_HOME = os.environ.get("PADDLEX_HOME", "/opt/paddleocr/models/.paddlex")

os.environ["PADDLEOCR_HOME"] = PADDLEOCR_HOME
os.environ["PADDLEX_HOME"] = PADDLEX_HOME

# Track last request time for idle detection
last_request_time = time.time()

s3_client = None

# Language code mapping
LANG_MAP = {
    "ko": "korean",
    "ja": "japan",
    "zh": "ch",
    "en": "en",
    "zh-tw": "chinese_cht",
}


def get_s3_client():
    global s3_client
    if s3_client is None:
        s3_client = boto3.client("s3")
    return s3_client


def map_language(lang: str) -> str:
    """Map short language codes to paddleocr language names."""
    if not lang:
        return None
    return LANG_MAP.get(lang, lang)


# Model cache
_model_cache: Dict[str, Any] = {}


def get_paddleocr_vl():
    """Get or create PaddleOCR-VL instance."""
    if "paddleocr-vl" not in _model_cache:
        logger.info("Loading PaddleOCR-VL model...")
        from paddleocr import PaddleOCRVL
        _model_cache["paddleocr-vl"] = PaddleOCRVL()
        logger.info("PaddleOCR-VL model loaded successfully")
    return _model_cache["paddleocr-vl"]


def get_pp_ocrv5(lang: str = None, options: Dict[str, Any] = None):
    """Get or create PP-OCRv5 instance.

    Supported options:
    - use_doc_orientation_classify: bool (default: False) - document orientation auto-correction
    - use_doc_unwarping: bool (default: False) - document distortion correction
    - use_textline_orientation: bool (default: False) - text line orientation detection
    """
    opts = options or {}
    mapped_lang = map_language(lang)

    # Create unique key based on lang and options
    opt_key = f"{opts.get('use_doc_orientation_classify', False)}_{opts.get('use_doc_unwarping', False)}_{opts.get('use_textline_orientation', False)}"
    key = f"pp-ocrv5-{mapped_lang or 'default'}-{opt_key}"

    if key not in _model_cache:
        logger.info(f"Loading PP-OCRv5 model with lang={mapped_lang}, options={opts}...")
        from paddleocr import PaddleOCR
        kwargs = {
            "use_doc_orientation_classify": opts.get("use_doc_orientation_classify", False),
            "use_doc_unwarping": opts.get("use_doc_unwarping", False),
            "use_textline_orientation": opts.get("use_textline_orientation", False),
        }
        if mapped_lang:
            kwargs["lang"] = mapped_lang
        _model_cache[key] = PaddleOCR(**kwargs)
        logger.info("PP-OCRv5 model loaded successfully")
    return _model_cache[key]


def get_pp_structurev3(lang: str = None, options: Dict[str, Any] = None):
    """Get or create PP-StructureV3 instance.

    Supported options:
    - use_doc_orientation_classify: bool (default: False) - document orientation auto-correction
    - use_doc_unwarping: bool (default: False) - document distortion correction
    """
    opts = options or {}
    mapped_lang = map_language(lang)

    # Create unique key based on lang and options
    opt_key = f"{opts.get('use_doc_orientation_classify', False)}_{opts.get('use_doc_unwarping', False)}"
    key = f"pp-structurev3-{mapped_lang or 'default'}-{opt_key}"

    if key not in _model_cache:
        logger.info(f"Loading PP-StructureV3 model with lang={mapped_lang}, options={opts}...")
        from paddleocr import PPStructureV3
        kwargs = {
            "use_doc_orientation_classify": opts.get("use_doc_orientation_classify", False),
            "use_doc_unwarping": opts.get("use_doc_unwarping", False),
        }
        if mapped_lang:
            kwargs["lang"] = mapped_lang
        _model_cache[key] = PPStructureV3(**kwargs)
        logger.info("PP-StructureV3 model loaded successfully")
    return _model_cache[key]


def format_vl_output(results: List[Any]) -> Dict[str, Any]:
    """Format PaddleOCR-VL output."""
    pages = []
    all_content = []

    for page_idx, res in enumerate(results):
        if hasattr(res, "json"):
            res_data = res.json.get("res", res.json)
            parsing_list = res_data.get("parsing_res_list", [])

            blocks = []
            content_parts = []

            for block in parsing_list:
                block_content = block.get("block_content", "").strip()
                block_label = block.get("block_label", "text")

                blocks.append({
                    "block_id": block.get("block_id", 0),
                    "block_label": block_label,
                    "block_content": block_content,
                    "block_bbox": block.get("block_bbox", []),
                    "block_order": block.get("block_order"),
                    "group_id": block.get("group_id", 0),
                })

                if block_content:
                    if block_label == "doc_title":
                        content_parts.append(f"# {block_content}")
                    elif block_label == "paragraph_title":
                        content_parts.append(f"## {block_content}")
                    else:
                        content_parts.append(block_content)

            page_content = "\n\n".join(content_parts)
            width = res_data.get("width")
            height = res_data.get("height")

            pages.append({
                "page_index": page_idx,
                "content": page_content,
                "blocks": blocks,
                "width": width,
                "height": height,
            })
            all_content.append(page_content)

    return {
        "success": True,
        "format": "markdown",
        "pages": pages,
        "page_count": len(pages),
        "content": "\n\n---\n\n".join(all_content),
    }


def format_ocr_output(results: List, model_name: str) -> Dict[str, Any]:
    """Format PP-OCRv5 output."""
    blocks = []
    content_parts = []

    if results:
        for page_idx, res in enumerate(results):
            if hasattr(res, "json"):
                res_data = res.json.get("res", {})
                rec_texts = res_data.get("rec_texts", [])
                rec_polys = res_data.get("rec_polys", [])

                for idx, text in enumerate(rec_texts):
                    bbox = []
                    if rec_polys and idx < len(rec_polys):
                        poly = rec_polys[idx]
                        if poly and len(poly) == 4:
                            xs = [p[0] for p in poly]
                            ys = [p[1] for p in poly]
                            bbox = [min(xs), min(ys), max(xs), max(ys)]

                    blocks.append({
                        "block_id": idx,
                        "block_label": "text",
                        "block_content": text,
                        "block_bbox": bbox,
                        "block_order": idx,
                    })

                    if text.strip():
                        content_parts.append(text.strip())

    page_content = "\n".join(content_parts)

    return {
        "success": True,
        "format": "markdown",
        "pages": [{
            "page_index": 0,
            "content": page_content,
            "blocks": blocks,
            "width": None,
            "height": None,
        }],
        "page_count": 1,
        "content": page_content,
    }


# Pydantic models
class PredictRequest(BaseModel):
    s3_uri: str
    model: str = "paddleocr-vl"
    model_options: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    last_request_seconds_ago: float
    models_loaded: List[str]


# FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting PaddleOCR inference server...")
    logger.info(f"MODEL_CACHE_BUCKET: {MODEL_CACHE_BUCKET}")
    os.makedirs(PADDLEOCR_HOME, exist_ok=True)
    os.makedirs(PADDLEX_HOME, exist_ok=True)
    yield
    logger.info("Shutting down PaddleOCR inference server...")


app = FastAPI(
    title="PaddleOCR Inference Server",
    description="OCR inference server for PaddleOCR models",
    version="2.0.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    global last_request_time
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        last_request_seconds_ago=time.time() - last_request_time,
        models_loaded=list(_model_cache.keys()),
    )


@app.post("/predict")
async def predict(request: PredictRequest):
    global last_request_time
    last_request_time = time.time()

    s3_uri = request.s3_uri
    model_name = request.model
    model_options = request.model_options
    metadata = request.metadata
    lang = model_options.get("lang")

    logger.info(f"Processing {s3_uri} with model={model_name}, lang={lang}")

    # Parse S3 URI
    s3_uri_clean = s3_uri.replace("s3://", "")
    bucket = s3_uri_clean.split("/")[0]
    key = "/".join(s3_uri_clean.split("/")[1:])

    # Download file to temp
    s3 = get_s3_client()
    suffix = os.path.splitext(key)[1].lower() or ".jpg"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        s3.download_file(bucket, key, tmp.name)
        tmp_path = tmp.name

    try:
        # Get model and run inference
        if model_name == "paddleocr-vl":
            model = get_paddleocr_vl()
            results = model.predict(input=tmp_path)
            output = format_vl_output(results)
        elif model_name == "pp-ocrv5":
            model = get_pp_ocrv5(lang, model_options)
            results = model.predict(input=tmp_path)
            output = format_ocr_output(results, model_name)
        elif model_name == "pp-structurev3":
            model = get_pp_structurev3(lang, model_options)
            results = model.predict(input=tmp_path)
            output = format_vl_output(results)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model: {model_name}. Available: paddleocr-vl, pp-ocrv5, pp-structurev3"
            )

        output["model"] = model_name
        output["model_options"] = model_options
        output["metadata"] = metadata

        logger.info(f"OCR complete: {output['page_count']} pages, {len(output.get('pages', [{}])[0].get('blocks', []))} blocks")
        return output

    except Exception as e:
        logger.error(f"Prediction error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
