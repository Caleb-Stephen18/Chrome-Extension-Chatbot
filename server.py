import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from typing import Dict, List
import logging
import uuid
import re

app = Flask(__name__)
CORS(app, resources={r"/": {"origins": ""}})

embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

vectorstores: Dict[str, FAISS] = {}

qa_template = """Use the following pieces of context to answer the question at the end. If you don't know the answer, just say that you don't know, don't try to make up an answer.

{context}

Question: {question}
Helpful Answer:"""

QA_PROMPT = PromptTemplate(template=qa_template, input_variables=["context", "question"])

question_generator_template = """
Based on the following webpage content, suggest 3 relevant questions that a user might want to ask:

Webpage content: {content}

Provide the questions in the following format:
Q1: [First question]
Q2: [Second question]
Q3: [Third question]
"""

question_generator_prompt = PromptTemplate(
    input_variables=["content"],
    template=question_generator_template
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# New function to interact with the external API
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
        response.raise_for_status()  # Raises an HTTPError for bad responses
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None

@app.route('/v2/process_page', methods=['POST'])
def process_page():
    logger.info("Process page endpoint called")
    if 'content' not in request.json:
        logger.warning("No content in request")
        return jsonify({'error': 'No content provided'}), 400
    
    content = request.json['content']
    url = request.json.get('url', '')
    logger.info(f"Processing page with content length: {len(content)}")
    logger.info(f"URL: {url}")
    
    try:
        create_vectorstore(content, url)
        initial_questions = generate_questions(content)
        
        return jsonify({
            'initial_questions': initial_questions,
            'status': 'success'
        })
    except Exception as e:
        logger.error(f"Error in process_page: {str(e)}")
        return jsonify({'error': str(e)}), 500

def create_vectorstore(content, url):
    global vectorstores
    try:
        text_splitter = CharacterTextSplitter(
            separator = "\n",
            chunk_size = 1000,
            chunk_overlap  = 200,
            length_function = len,
        )
        texts = text_splitter.split_text(content)
        logger.info(f"Split into {len(texts)} chunks")
        
        vectorstores[url] = FAISS.from_texts(texts, embeddings, metadatas=[{"source": url}] * len(texts))
        
        logger.info("Vector store created successfully")
    except Exception as e:
        logger.error(f"Error in create_vectorstore: {str(e)}")
        raise

import re

def generate_questions(content):
    try:
        prompt = question_generator_prompt.format(content=content)
        response = query_external_api(prompt)
        
        if response and isinstance(response, dict) and 'text' in response:
            text = response['text']
            
            # First, try to find questions within <h3> tags
            questions = re.findall(r'<h3>(Q\d+:.*?)</h3>', text)
            
            if not questions:
                # If no <h3> tags, try to find questions in the plain text
                questions = re.findall(r'Q\d+:.*?(?=Q\d+:|$)', text, re.DOTALL)
            
            # Clean up the questions by removing HTML tags and extra whitespace
            cleaned_questions = []
            for q in questions:
                # Remove HTML tags
                cleaned_q = re.sub(r'<.*?>', '', q)
                # Remove extra whitespace
                cleaned_q = re.sub(r'\s+', ' ', cleaned_q).strip()
                cleaned_questions.append(cleaned_q)
            
            return cleaned_questions
        else:
            logger.error(f"Unexpected response structure: {response}")
            return []
    except Exception as e:
        logger.error(f"Error in generate_questions: {str(e)}")
        return []

@app.route('/v2/ask_question', methods=['POST'])
def ask_question():
    logger.info("\n--- New question received ---")
    logger.info(f"Request data: {request.json}")
    
    if not vectorstores:
        logger.info("No pages processed yet")
        return jsonify({'error': 'Please process a page first'}), 400

    if 'query' not in request.json:
        logger.info("No query in request")
        return jsonify({'error': 'No query provided'}), 400

    query = request.json['query']
    current_url = request.json.get('currentUrl', '')
    processed_urls = request.json.get('processedUrls', [])
    logger.info(f"Received question: {query}")
    logger.info(f"Current URL: {current_url}")
    logger.info(f"Processed URLs: {processed_urls}")

    result = tiered_search(query, current_url, processed_urls)
    answer = result['answer']
    context = result.get('context', '')

    logger.info(f"Final answer: {answer}")

    if answer == "I couldn't find a relevant answer in the current or previous pages.":
        full_content = ""
        for url in processed_urls:
            if url in vectorstores:
                docs = vectorstores[url].similarity_search("", k=100)
                full_content += "\n".join(doc.page_content for doc in docs)
        suggested_questions = generate_questions(full_content)
    else:
        suggested_questions = generate_questions(context)

    return jsonify({
        'answer': answer,
        'sources': result.get('sources', []),
        'suggested_questions': suggested_questions
    })

def tiered_search(query: str, current_url: str, processed_urls: List[str]):
    logger.info(f"\nPerforming tiered search for query: {query}")
    logger.info(f"Current URL: {current_url}")
    logger.info(f"Processed URLs: {processed_urls}")
    
    if current_url in vectorstores:
        logger.info(f"Searching current URL: {current_url}")
        result = search_single_store(query, vectorstores[current_url])
        if result['answer'].strip() and not result['answer'].lower().startswith("i don't know"):
            logger.info(f"Answer found in current URL: {current_url}")
            return result
    
    for url in reversed(processed_urls):
        if url != current_url and url in vectorstores:
            logger.info(f"Searching previous URL: {url}")
            result = search_single_store(query, vectorstores[url])
            if result['answer'].strip() and not result['answer'].lower().startswith("i don't know"):
                logger.info(f"Answer found in previous URL: {url}")
                return result
    
    logger.info("No answer found in any processed URLs")
    return {"answer": "I couldn't find a relevant answer in the current or previous pages.", "source_documents": [], "context": ""}

def search_single_store(query: str, store: FAISS):
    docs = store.similarity_search(query, k=3)
    
    logger.info(f"\nQuery: {query}")
    logger.info("Retrieved context chunks:")
    for i, doc in enumerate(docs, 1):
        logger.info(f"Chunk {i}:")
        logger.info(doc.page_content)
        logger.info(f"Metadata: {doc.metadata}")
        logger.info("-" * 50)
    
    context = "\n".join(doc.page_content for doc in docs)
    
    prompt = QA_PROMPT.format(context=context, question=query)
    response = query_external_api(prompt)
    
    if response and isinstance(response, dict) and 'text' in response:
        answer = response['text']
        # Remove HTML tags if present
        answer = re.sub(r'<.*?>', '', answer)
        answer = answer.strip()
    else:
        logger.error(f"Unexpected response structure: {response}")
        answer = "I'm sorry, I couldn't generate an answer at this time."
    
    return {
        "answer": answer,
        "source_documents": docs,
        "context": context
    }


if __name__ == '__main__':
    app.run(debug=True, use_reloader = False)