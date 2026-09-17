#!/usr/bin/env python3
"""
Debug script to list available Gemini models
Helps identify the correct model name to use
"""
import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

# Configure with API key
api_key = os.getenv("GEMINI_API_KEY") or "AIzaSyALpGJX6HWYrEhP0zwp2at0wEajbQR-gJA"
genai.configure(api_key=api_key)

print("="*60)
print("GEMINI MODELS DIAGNOSTIC")
print("="*60)
print(f"\nAPI Key configured: {api_key[:20]}...\n")

try:
    print("Listing available models with 'generateContent' support:\n")
    models = genai.list_models()
    
    available_models = []
    for model in models:
        if 'generateContent' in model.supported_generation_methods:
            available_models.append(model.name)
            print(f"  ✓ {model.name}")
    
    print(f"\n{'='*60}")
    print(f"Total models available: {len(available_models)}")
    print(f"{'='*60}\n")
    
    # Test common model names
    print("Testing common model names:\n")
    test_models = [
        'gemini-pro',
        'gemini-1.5-flash',
        'gemini-1.5-pro',
        'gemini-1.0-pro',
        'models/gemini-pro',
        'models/gemini-1.5-flash',
    ]
    
    for model_name in test_models:
        try:
            model = genai.GenerativeModel(model_name)
            # Try a simple test
            response = model.generate_content("Say hello")
            print(f"  ✓ {model_name}: WORKS (response: {response.text[:50]}...)")
        except Exception as e:
            error_msg = str(e)
            if '404' in error_msg:
                print(f"  ✗ {model_name}: 404 NOT FOUND")
            else:
                print(f"  ✗ {model_name}: ERROR - {error_msg[:60]}")
    
    print(f"\n{'='*60}")
    print("RECOMMENDATION:")
    print("Use the model name that shows 'WORKS' above")
    print(f"{'='*60}\n")
    
except Exception as e:
    print(f"Error listing models: {e}")
    import traceback
    traceback.print_exc()

