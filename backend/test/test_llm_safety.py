from langchain_google_genai import ChatGoogleGenerativeAI
import pydantic

try:
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        safety_settings={
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_ONLY_HIGH"
        }
    )
    print("Format 1 (dict) worked")
except Exception as e:
    print(f"Format 1 failed: {e}")

try:
    from langchain_google_genai import HarmCategory, HarmBlockThreshold
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        safety_settings={
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH
        }
    )
    print("Format 2 (enums in dict) worked")
except Exception as e:
    print(f"Format 2 failed: {e}")

try:
    llm = ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        safety_settings=[
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"}
        ]
    )
    print("Format 3 (list of dicts) worked")
except Exception as e:
    print(f"Format 3 failed: {e}")
