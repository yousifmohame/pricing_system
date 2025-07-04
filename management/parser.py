# management/parser.py
import os
import json
import google.generativeai as genai

def parse_with_ai(text):
    """
    Parses raw text into a list of OFFER GROUPS, with an enhanced prompt for region extraction.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return [{"error": "Google API key is not configured."}]

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')

    # --- MASTER PROMPT v3.0 (Enhanced for Region Detection) ---
    prompt = f"""
    You are an expert data extraction system. Your primary task is to analyze raw text from supplier offers and transform it into a structured JSON object.
    The root of the JSON object must be a key named "offer_groups", which contains an array of offer group objects.

    **CRITICAL INSTRUCTIONS:**
    1.  **`grouping_name`:** This MUST be the main, recognizable product name (e.g., "Apple iPhone 16 Pro", "Samsung Galaxy S24 Ultra").
    2.  **`spec_region`:** Actively look for any mention of a country, region, or specification (e.g., "USA", "Japan", "International", "Global", "Middle East", "KSA", "UAE", "Vietnam"). This is a very important field. If you find a general context at the start of the text (like "Arabic Vietnam"), apply it to all subsequent offers unless an offer has its own specific region.
    3.  **`variants`**: This array should contain the specific details that differ between items in the same group (like color, specific storage, etc.).

    Each object in the "offer_groups" array MUST have these keys:
    - "grouping_name": string (Example: "Apple iPhone 16 Pro").
    - "brand_name": string (Example: "Apple").
    - "category_name": string (Infer from: ["Phones", "Tablets", "Laptops", "Watches", "Accessories"]).
    - "variants": array of objects. Each variant object MUST have these keys:
        - "name": string (The specific detail, e.g., "256GB DESERT").
        - "quantity": integer.
        - "price": float.
        - "currency": string (Default to 'USD').
        - "storage": string.
        - "color": string.
        - "condition": string (Default to 'New').
        - "spec_region": string (The region or specification you identified).

    Your entire response MUST be ONLY a valid JSON object starting with `{{"offer_groups": [...]}}`.
    ---
    EXAMPLE 1:
    TEXT: "iPhone 15 Pro Max Japan spec"
    JSON: {{"offer_groups": [{{"grouping_name": "Apple iPhone 15 Pro Max", "brand_name": "Apple", "category_name": "Phones", "variants": [{{"name": "Japan spec", "spec_region": "Japan", "quantity": 1, "price": null, "currency": "USD", "storage": null, "color": null, "condition": "New"}}]}}]}}

    EXAMPLE 2:
    TEXT: "S24 Ultra, Vietnam Version, 256GB, Black, 50 pcs"
    JSON: {{"offer_groups": [{{"grouping_name": "Samsung S24 Ultra", "brand_name": "Samsung", "category_name": "Phones", "variants": [{{"name": "256GB Black", "spec_region": "Vietnam", "quantity": 50, "price": null, "currency": "USD", "storage": "256GB", "color": "Black", "condition": "New"}}]}}]}}
    ---
    TEXT TO ANALYZE:
    {text}
    """
    try:
        generation_config = genai.GenerationConfig(response_mime_type="application/json")
        response = model.generate_content(prompt, generation_config=generation_config)
        parsed_json = json.loads(response.text)
        return parsed_json.get("offer_groups", [])
    except Exception as e:
        print(f"An error occurred with the API: {e}")
        return [{"error": f"Failed to parse with AI. Details: {str(e)}"}]

def find_best_shipping_keyword_with_ai(product_name, shipping_rates_list):
    """Uses AI to find the best matching shipping keyword."""
    if not shipping_rates_list: return None
    
    keywords = [rate.product_keyword_en for rate in shipping_rates_list if rate.product_keyword_en]
    if not keywords: return None

    prompt = f"""
    Analyze the product name: "{product_name}".
    From the following list of shipping keywords: {keywords}.
    Which single keyword is the most appropriate semantic match?
    Respond with ONLY the single best-matching keyword string. If no good match, respond with "None".
    """
    try:
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key: return None
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        response = model.generate_content(prompt)
        best_keyword = response.text.strip()
        return best_keyword if best_keyword in keywords else None
    except Exception as e:
        print(f"AI Shipping search failed: {e}")
        return None

def parse_document_with_ai(file_content_base64, mime_type):
    """Analyzes an image or PDF file content (a shipping price list)."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key: return {"error": "Google API key is not configured."}
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    prompt = """
    You are a data extraction expert. Analyze the provided document.
    Your task is to extract the data into a structured JSON object.
    The root of the JSON object must be a key named "shipping_rates" which contains an array of rate objects.
    Each object in the "shipping_rates" array MUST have these keys:
    - "product_keyword_en": string (The item name in English).
    - "product_keyword_ar": string (The item name in Arabic).
    - "cost": float (The price).
    - "currency": string (The currency, e.g., 'AED').
    Your entire response MUST be ONLY the JSON object.
    """
    image_part = {"mime_type": mime_type, "data": file_content_base64}
    try:
        response = model.generate_content([prompt, image_part])
        json_text = response.text.strip().replace('```json', '').replace('```', '')
        parsed_json = json.loads(json_text)
        return parsed_json.get("shipping_rates", [])
    except Exception as e:
        print(f"An error occurred with the Vision API: {e}")
        return {"error": f"Failed to analyze document. Details: {str(e)}"}
