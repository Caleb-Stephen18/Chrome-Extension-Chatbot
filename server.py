from flask import Flask, request, jsonify
from flask_cors import CORS
from langchain.prompts import PromptTemplate
import logging
import uuid
import requests
import re
import time

app = Flask(__name__)
CORS(app, resources={r"/": {"origins": ""}})

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

qa_template = """Use the following pieces of context to answer the question at the end. If you don't know the answer, just say that you don't know, don't try to make up an answer.

{context}

Question: {question}
Helpful Answer:"""

QA_PROMPT = PromptTemplate(template=qa_template, input_variables=["context", "question"])

question_generator_template = """
Given the following initial context: {initial_context}

Suggest 3 relevant questions that a user might want to ask about the website or its services.

Provide the questions in the following format:
Q1: [First question]
Q2: [Second question]
Q3: [Third question]
"""

question_generator_prompt = PromptTemplate(
    input_variables=["initial_context"],
    template=question_generator_template
)

def query_external_api(prompt):
    url = "https://excellence-ecs-service-cert.zuro-dev-devl-vpn.us.e01.c01.getzuro.com/chat/claude"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    data = {
        "connectionId": str(uuid.uuid4()),
        "body": {
            "action": "chat",
            "data": {
                "org_id": "org_1ULYDscOZafKCrcT",
                "widget_id": "63930269-0e95-4cfa-9d15-fdbb6522d249",
                "conversation_id": str(uuid.uuid4()),
                "prompt": prompt
            }
        }
    }
    
    try:
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None

def generate_questions(initial_context="", retries=3, delay=2):
    for attempt in range(retries):
        try:
            prompt = question_generator_prompt.format(initial_context=initial_context)
            response = query_external_api(prompt)
            
            if response and isinstance(response, dict) and 'text' in response:
                text = response['text']
                
                questions = re.findall(r'Q\d+:.*?(?=Q\d+:|$)', text, re.DOTALL)
                
                cleaned_questions = [re.sub(r'<.*?>', '', q.strip()) for q in questions]
                cleaned_questions = [re.sub(r'^Q\d+:\s*', '', q) for q in cleaned_questions]
                cleaned_questions = [re.sub(r'\s+', ' ', q) for q in cleaned_questions]
                
                if cleaned_questions:
                    return cleaned_questions
            
            logger.warning(f"Failed to generate questions on attempt {attempt + 1}")
            if attempt < retries - 1:
                time.sleep(delay)
        except Exception as e:
            logger.error(f"Error in generate_questions: {str(e)}")
            if attempt < retries - 1:
                time.sleep(delay)
    
    logger.error("Failed to generate questions after all attempts")
    return []

@app.route('/ask_question', methods=['POST'])
def ask_question():
    logger.info("New question received")
    
    if 'query' not in request.json:
        logger.info("No query in request")
        return jsonify({'error': 'No query provided'}), 400

    query = request.json['query']
    logger.info(f"Received question: {query}")

    prompt = QA_PROMPT.format(context="", question=query)
    response = query_external_api(prompt)
    
    if response and isinstance(response, dict) and 'text' in response:
        answer = response['text'].strip()
        # Remove HTML tags
        answer = re.sub(r'<.*?>', '', answer)
    else:
        logger.error(f"Unexpected response structure: {response}")
        answer = "I'm sorry, I couldn't generate an answer at this time."

    logger.info(f"Final answer: {answer}")

    suggested_questions = generate_questions(initial_context=query)

    return jsonify({
        'answer': answer,
        'suggested_questions': suggested_questions
    })

@app.route('/get_initial_questions', methods=['GET'])
def get_initial_questions():
    suggested_questions = generate_questions(initial_context="Give me some initial questions to get started")
    return jsonify({
        'suggested_questions': suggested_questions
    })

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)