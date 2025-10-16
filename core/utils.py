import pdfplumber
import docx
import spacy

# Load spaCy model once
nlp = spacy.load("en_core_web_sm")

def extract_text_from_resume(file_path, ext):
    """
    Extracts text from a resume file.
    Supports PDF and DOCX.
    """
    if ext == 'pdf':
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    elif ext in ['doc', 'docx']:
        doc = docx.Document(file_path)
        text = "\n".join([p.text for p in doc.paragraphs])
        return text
    else:
        # For unsupported formats, return empty string
        return ""

def extract_skills(text, skills_list=None):
    """
    Extracts known skills from text.
    skills_list can be provided or use a default set.
    """
    if not skills_list:
        skills_list = [
            "Python", "Java", "Excel", "Machine Learning", "Django", "React", "SQL",
            "Project Management", "Communication", "Leadership", "AWS", "Docker"
        ]
    text_lower = text.lower()
    return [skill for skill in skills_list if skill.lower() in text_lower]

def extract_experience(text):
    """
    Naively extracts sentences mentioning experience or work.
    Returns a list of sentences.
    """
    doc = nlp(text)
    experiences = []
    for sent in doc.sents:
        if ("experience" in sent.text.lower() or 
            "worked at" in sent.text.lower() or 
            "role:" in sent.text.lower() or 
            "position:" in sent.text.lower()):
            experiences.append(sent.text.strip())
    return experiences

def extract_education(text):
    """
    Naively extracts sentences mentioning education or university.
    Returns the first matching sentence.
    """
    doc = nlp(text)
    for sent in doc.sents:
        if ("university" in sent.text.lower() or "bachelor" in sent.text.lower() or
            "degree" in sent.text.lower() or "college" in sent.text.lower() or
            "master" in sent.text.lower()):
            return sent.text.strip()
    return ""

def calculate_match_score(resume_skills, job_requirements):
    """
    Calculates match score as ratio of overlapping skills to required skills.
    Returns float between 0 and 1.
    """
    if not resume_skills or not job_requirements:
        return 0.0
    resume_set = set([s.lower() for s in resume_skills])
    job_set = set([r.lower() for r in job_requirements])
    overlap = resume_set.intersection(job_set)
    score = len(overlap) / len(job_set)
    return round(score, 2)