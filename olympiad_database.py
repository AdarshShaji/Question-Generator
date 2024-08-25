from supabase import create_client, Client
from olympiad_config import OLYMPIAD_SUBJECTS, SUPABASE_URL, SUPABASE_KEY
from olympiad_question_bank import get_question as get_question_from_bank
import streamlit as st
import pandas as pd
import logging
import requests


# Set up logging
logging.basicConfig(level=logging.INFO)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_user_lexile(student_id):
    try:
        response = supabase.table('users').select('lexile_level').eq('student_id', student_id).execute()
        if response.data:
            return response.data[0]['lexile_level']
        return None
    except Exception as e:
        print(f"Error getting user Lexile level: {str(e)}")
        return None

def get_subjects():
    try:
        response = supabase.table('subjects').select('id', 'name').execute()
        return {subject['id']: subject['name'] for subject in response.data}
    except Exception as e:
        print(f"Error fetching subjects: {str(e)}")
        return {}

def get_lexile_levels():
    try:
        response = supabase.table('lexile_levels').select('id', 'level').execute()
        return {level['id']: level['level'] for level in response.data}
    except Exception as e:
        print(f"Error fetching lexile levels: {str(e)}")
        return {}

def get_subject_id_by_name(subject_name):
    subjects = get_subjects()
    return next((id for id, name in subjects.items() if name == subject_name), None)

def get_lexile_id_by_level(lexile_level):
    lexile_levels = get_lexile_levels()
    return next((id for id, level in lexile_levels.items() if level == lexile_level), None)

def save_olympiad_result(student_id, subject, score, time_limit, accuracy, total_questions, difficulty):
    try:
        print(f"Attempting to save result for student {student_id}")
        result = supabase.table('olympiad_results').insert({
            'student_id': student_id,
            'subject': subject,
            'score': score,
            'time_limit': time_limit,
            'accuracy': accuracy,
            'total_questions': total_questions,
            'difficulty': difficulty
        }).execute()
        if result.data:
            print("Data inserted successfully")
        else:
            print("Data insertion failed")
        print(f"Saved Olympiad result for user {student_id}: {result}")
        return result
        
    except Exception as e:
        print(f"Error saving Olympiad result: {str(e)}")
        return None

def get_olympiad_results(student_id):
    try:
        results = supabase.table('olympiad_results').select('*').eq('student_id', student_id).order('created_at', desc=True).execute()
        return results.data
    except Exception as e:
        print(f"Error getting Olympiad results: {str(e)}")
        return []

def get_question(subject, difficulty, lexile_level):
    logging.debug(f"get_question called with subject={subject}, difficulty={difficulty}, lexile_level={lexile_level}")
    try:
        subject_id = get_subject_id_by_name(subject)
        logging.debug(f"Retrieved subject_id: {subject_id}")
        
        # Get all available lexile levels
        lexile_levels = get_lexile_levels()
        logging.debug(f"Available lexile levels: {lexile_levels}")
        
        # Find the next higher lexile level
        next_higher_lexile = min((level for level in lexile_levels.values() if level >= lexile_level), default=None)
        logging.debug(f"Next higher lexile level: {next_higher_lexile}")
        
        if next_higher_lexile is None:
            logging.warning(f"No suitable lexile level found for {lexile_level}")
            return None
        
        lexile_id = get_lexile_id_by_level(next_higher_lexile)
        logging.debug(f"Retrieved lexile_id: {lexile_id}")
        
        if subject_id is None or lexile_id is None:
            logging.warning("subject_id or lexile_id is None")
            return None
        
        response = supabase.table('questions').select('*').eq('subject_id', subject_id).eq('difficulty', difficulty).eq('lexile_level_id', lexile_id).order('RANDOM()').limit(1).execute()
        logging.debug(f"Supabase response: {response}")
        
        if response.data:
            logging.debug(f"Returning question: {response.data[0]}")
            return response.data[0]
        else:
            logging.warning(f"No questions found for subject_id={subject_id}, difficulty={difficulty}, lexile_level_id={lexile_id}")
            return None
    except Exception as e:
        logging.error(f"Error getting question: {str(e)}")
        return None
    
def save_question(subject, difficulty, lexile_level, question, options, correct_answer):
    try:
        logging.info(f"Attempting to save question: {subject}, difficulty: {difficulty}, lexile: {lexile_level}, question: {question[:30]}...")
        
        subject_id = get_subject_id_by_name(subject)
        lexile_id = get_lexile_id_by_level(lexile_level)
        
        if subject_id is None or lexile_id is None:
            return False, "Invalid subject or lexile level"
        
        data = {
            'subject_id': subject_id,
            'difficulty': difficulty,
            'lexile_level_id': lexile_id,
            'question': question,
            'options': ','.join(options),
            'correct_answer': correct_answer
        }
        logging.info(f"Data prepared: {data}")
        
        response = supabase.table('questions').insert(data).execute()
        logging.info(f"Supabase response: {response}")
        
        if response.data:
            logging.info("Question saved successfully")
            return True, "Question saved successfully"
        else:
            logging.error("No data returned from Supabase")
            return False, "No data returned from Supabase"
    except Exception as e:
        logging.error(f"Unexpected error saving question: {str(e)}")
        return False, f"An unexpected error occurred: {str(e)}"

def get_student_performance(student_id, subject):
    try:
        results = supabase.table('olympiad_results').select('*').eq('student_id', student_id).eq('subject', subject).execute()
        return results.data
    except Exception as e:
        print(f"Error getting student performance: {str(e)}")
        return []

def get_percentile_ranking(user_id, subject):
    user_score = supabase.table('olympiad_results').select('score').eq('student_id', user_id).eq('subject', subject).order('created_at', desc=True).limit(1).execute().data[0]['score']
    
    all_scores = supabase.table('olympiad_results').select('score').eq('subject', subject).execute().data
    all_scores = [score['score'] for score in all_scores]
    
    percentile = sum(score <= user_score for score in all_scores) / len(all_scores) * 100
    return percentile

def display_percentile_rankings(user_id):
    st.subheader("Percentile Rankings")
    for subject in OLYMPIAD_SUBJECTS:
        percentile = get_percentile_ranking(user_id, subject)
        st.write(f"{subject}: {percentile:.2f}th percentile")

def get_topic_performance(student_id, subject):
    try:
        results = supabase.table('olympiad_results').select('*').eq('student_id', student_id).eq('subject', subject).execute()
        df = pd.DataFrame(results.data)
        
        # Assuming we have a 'topic' column in our results
        # If not, we need to modify our database schema to include topics
        topic_performance = df.groupby('topic')['score'].mean().to_dict()
        return topic_performance
    except Exception as e:
        print(f"Error getting topic performance: {str(e)}")
        return {}

def get_difficulty_progression(student_id, subject):
    try:
        results = supabase.table('olympiad_results').select('*').eq('student_id', student_id).eq('subject', subject).order('created_at').execute()
        df = pd.DataFrame(results.data)
        
        difficulty_progression = df.set_index('created_at')['difficulty'].to_dict()
        return difficulty_progression
    except Exception as e:
        print(f"Error getting difficulty progression: {str(e)}")
        return {}

def get_progress_data(student_id):
    try:
        results = supabase.table('olympiad_results').select('*').eq('student_id', student_id).order('created_at').execute()
        df = pd.DataFrame(results.data)
        
        print(f"Retrieved data: {df.to_dict()}")  # Debug print
        
        if df.empty:
            print("No data found for the student")
            return pd.DataFrame()
        
        progress_data = df.groupby(['subject', 'created_at'])['score'].mean().unstack(level=0)
        return progress_data
    except Exception as e:
        print(f"Error getting progress data: {str(e)}")
        return pd.DataFrame()

def get_user_goals(student_id):
    try:
        # Assuming we have a 'user_goals' table in our database
        goals = supabase.table('user_goals').select('*').eq('student_id', student_id).execute()
        return goals.data
    except Exception as e:
        print(f"Error getting user goals: {str(e)}")
        return []

def calculate_goal_progress(student_id, goal):
    # This function would need to be implemented based on the structure of your goals
    # and how progress is measured. Here's a simple example:
    try:
        current_score = supabase.table('olympiad_results').select('score').eq('student_id', student_id).eq('subject', goal['subject']).order('created_at', desc=True).limit(1).execute().data[0]['score']
        progress = min(current_score / goal['target_score'], 1.0)  # Ensures progress is between 0 and 1
        return progress
    except Exception as e:
        print(f"Error calculating goal progress: {str(e)}")
        return 0
    
def get_olympiad_results(student_id):
    try:
        print(f"Fetching Olympiad results for student {student_id}")
        results = supabase.table('olympiad_results').select('*').eq('student_id', student_id).order('created_at', desc=True).execute()
        print(f"Retrieved {len(results.data)} results")
        return results.data
    except Exception as e:
        print(f"Error getting Olympiad results: {str(e)}")
        return []