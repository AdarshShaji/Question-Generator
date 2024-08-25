import streamlit as st
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.text_splitter import CharacterTextSplitter
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from olympiad_config import API_KEY, MODEL_NAME, QUESTIONS_MD_PATH
from olympiad_database import save_question, get_subjects, get_lexile_levels
import re

st.set_page_config(page_title="Olympiad Question Generator", layout="wide")

# Load the markdown file
with open(QUESTIONS_MD_PATH, "r") as f:
    md_content = f.read()

# Split the content into chunks
text_splitter = CharacterTextSplitter(chunk_size=1000, chunk_overlap=0)
texts = text_splitter.split_text(md_content)

# Initialize the embedding model
embeddings = HuggingFaceEmbeddings()

# Create the vector store
vectorstore = FAISS.from_texts(texts, embeddings)

# Initialize the Gemini model
llm = ChatGoogleGenerativeAI(google_api_key=API_KEY, model=MODEL_NAME)

question_generation_template = """
You are an AI assistant trained to generate educational multiple-choice questions (MCQs) for students.
Use the following reference questions and information to generate a new, similar Olympiad-style question with four multiple-choice options.
The new question should be on the topic of {subject} at difficulty level {difficulty} on a scale of 1 to 5, where 1 is easiest and 5 is most difficult.
The question should be suitable for a student with a Lexile level of {lexile}.

Reference information:
{context}

Please generate a new question that is similar in style and difficulty to the reference, but not identical.

Format your response EXACTLY as follows:
Question:
[Your generated question here]

Options:
A) [Option A]
B) [Option B] 
C) [Option C]
D) [Option D]

Correct Answer: [Correct option letter]
"""

question_prompt = PromptTemplate(
    template=question_generation_template,
    input_variables=["subject", "difficulty", "lexile", "context"]
)

retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

class QuestionGeneratorChain(LLMChain):
    @property
    def input_keys(self):
        return ["subject", "difficulty", "lexile"]

    def generate(self, subject, difficulty, lexile, run_manager=None):
        context = retriever.get_relevant_documents(f"{subject} difficulty {difficulty}")
        context_text = "\n".join([doc.page_content for doc in context])
        return self({"subject": subject, "difficulty": difficulty, "lexile": lexile, "context": context_text}, run_manager=run_manager)

question_chain = QuestionGeneratorChain(llm=llm, prompt=question_prompt)

def parse_generated_text(text):
    question_pattern = r'Question:\s*(.+?)(?=\n\s*Options:|\Z)'
    options_pattern = r'Options:\s*\nA\)\s*(.+)\s*\nB\)\s*(.+)\s*\nC\)\s*(.+)\s*\nD\)\s*(.+)'
    correct_answer_pattern = r'Correct Answer:\s*(\w)'

    question_match = re.search(question_pattern, text, re.DOTALL)
    options_match = re.search(options_pattern, text, re.DOTALL)
    correct_answer_match = re.search(correct_answer_pattern, text)

    if question_match and options_match and correct_answer_match:
        question = question_match.group(1).strip()
        options = [option.strip() for option in options_match.groups()]
        correct_answer = correct_answer_match.group(1).strip()
        return question, options, correct_answer
    else:
        return None, None, None

def generate_question(subject, difficulty, lexile):
    result = question_chain.generate(subject=subject, difficulty=difficulty, lexile=lexile)
    question, options, correct_answer = parse_generated_text(result['text'])
    return {
        "subject": subject,
        "difficulty": difficulty,
        "lexile_level": lexile,
        "question": question,
        "options": options,
        "correct_answer": ord(correct_answer) - ord('A') if correct_answer else None,
    }

def main():
    st.title("🏆 Olympiad Question Generator (RAG-powered)")
    st.write("Generate and review high-quality questions for Olympiad preparation, based on existing questions.")

    subjects = get_subjects()
    lexile_levels = get_lexile_levels()

    st.subheader("Question Generation")
    subject = st.selectbox("Select Subject", list(subjects.values()))
    difficulty = st.slider("Select Difficulty Level", 1, 5, 3)
    lexile = st.selectbox("Select Lexile Level", list(lexile_levels.values()))

    if 'questions' not in st.session_state:
        st.session_state.questions = []

    if st.button("Generate Questions", key="generate"):
        with st.spinner("Generating questions..."):
            st.session_state.questions = [generate_question(subject, difficulty, lexile) for _ in range(5)]  # Change 5 to the desired number of questions

    if st.session_state.questions:
        st.subheader("Generated Questions")
        for i, question_data in enumerate(st.session_state.questions):
            with st.expander(f"Question {i+1}"):
                st.write(question_data['question'])
                for j, option in enumerate(question_data['options']):
                    st.write(f"{chr(65+j)}) {option}")
                if question_data['correct_answer'] is not None:
                    correct_letter = chr(question_data['correct_answer'] + ord('A'))
                    st.write(f"**Correct Answer:** {correct_letter}")
                else:
                    st.write("**Error:** Correct answer not found")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🟩 Approve", key=f"approve_{i}"):
                        success, message = save_question(**question_data)
                        if success:
                            st.success("Question saved successfully!")
                        else:
                            st.error(f"Failed to save question: {message}")
                with col2:
                    if st.button("🟥 Reject", key=f"reject_{i}"):
                        st.warning("Question rejected and will not be saved.")

if __name__ == "__main__":
    main()