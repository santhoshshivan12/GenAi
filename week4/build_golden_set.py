from __future__ import annotations

import sys
from pathlib import Path

# Fix sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from reset_data import reset_store_data
from rag.service import RAGService

WEEK4_DIR = Path("week4")
WEEK4_DIR.mkdir(exist_ok=True)

def find_best_chunk(chunks, keywords, filename_contains=None):
    candidates = []
    for c in chunks:
        if filename_contains and filename_contains.lower() not in c.document_filename.lower():
            continue
        text_lower = c.text.lower()
        score = sum(1 for kw in keywords if kw.lower() in text_lower)
        if score > 0:
            candidates.append((score, c))
    candidates.sort(key=lambda x: x[0], reverse=True)
    if candidates:
        return candidates[0][1]
    
    # Fallback to any chunk matching filename_contains
    for c in chunks:
        if filename_contains and filename_contains.lower() in c.document_filename.lower():
            return c
    return chunks[0] if chunks else None

def main():
    print("Resetting store data for clean 6-doc corpus...")
    reset_store_data()
    svc = RAGService()
    chunks = svc.store.list_chunks()
    docs = svc.store.list_documents()
    print(f"Ingested Docs: {len(docs)}, Total Chunks: {len(chunks)}")

    # 12 Evaluation Questions (4 Dio, 4 Firebase Auth, 4 GoRouter)
    specifications = [
        # Dio (4)
        {
            "id": "Q01",
            "question": "How do you create a Dio instance with default options?",
            "keywords": ["Dio()", "BaseOptions", "default", "Dio"],
            "doc_filter": "dio",
            "is_exact_token": False
        },
        {
            "id": "Q02",
            "question": "What property is used to configure the connection timeout in Dio?",
            "keywords": ["connectTimeout", "BaseOptions", "timeout"],
            "doc_filter": "dio",
            "is_exact_token": True
        },
        {
            "id": "Q03",
            "question": "Which exception type is thrown when a receive timeout occurs?",
            "keywords": ["receiveTimeout", "DioExceptionType", "exception"],
            "doc_filter": "dio",
            "is_exact_token": True
        },
        {
            "id": "Q04",
            "question": "What response type should be used to receive raw bytes from a Dio request?",
            "keywords": ["ResponseType.bytes", "bytes", "responseType"],
            "doc_filter": "dio",
            "is_exact_token": True
        },
        # Firebase Auth (4)
        {
            "id": "Q05",
            "question": "How do you listen to user authentication state changes in Firebase Auth?",
            "keywords": ["authStateChanges", "userChanges", "listen"],
            "doc_filter": "firebase_auth",
            "is_exact_token": True
        },
        {
            "id": "Q06",
            "question": "What method is used to sign in with email and password in Firebase Auth?",
            "keywords": ["signInWithEmailAndPassword", "email", "password"],
            "doc_filter": "firebase_auth",
            "is_exact_token": True
        },
        {
            "id": "Q07",
            "question": "What property checks the currently signed in user in Firebase Auth?",
            "keywords": ["currentUser", "User", "instance"],
            "doc_filter": "firebase_auth",
            "is_exact_token": False
        },
        {
            "id": "Q08",
            "question": "How do you sign out a user from Firebase Auth?",
            "keywords": ["signOut", "signOut()", "logout"],
            "doc_filter": "firebase_auth",
            "is_exact_token": False
        },
        # GoRouter (4)
        {
            "id": "Q09",
            "question": "Which GoRouter feature allows an inner Navigator to be displayed while keeping a BottomNavigationBar visible?",
            "keywords": ["ShellRoute", "Navigator", "BottomNavigationBar"],
            "doc_filter": "go_router",
            "is_exact_token": True
        },
        {
            "id": "Q10",
            "question": "How do you define path parameters in GoRouter routes?",
            "keywords": ["pathParameters", "state.pathParameters", ":id"],
            "doc_filter": "go_router",
            "is_exact_token": False
        },
        {
            "id": "Q11",
            "question": "How do you configure redirection logic in GoRouter?",
            "keywords": ["redirect", "GoRouterState", "BuildContext"],
            "doc_filter": "go_router",
            "is_exact_token": False
        },
        {
            "id": "Q12",
            "question": "How do you trigger imperative navigation to a route in GoRouter?",
            "keywords": ["context.go", "context.push", "go"],
            "doc_filter": "go_router",
            "is_exact_token": False
        }
    ]

    golden_set = []
    for spec in specifications:
        matched_chunk = find_best_chunk(chunks, spec["keywords"], spec["doc_filter"])
        if not matched_chunk:
            raise ValueError(f"Failed to find matching chunk for {spec['id']}: {spec['question']}")
        
        golden_set.append({
            "id": spec["id"],
            "question": spec["question"],
            "correct_chunk_id": matched_chunk.id,
            "source_file": matched_chunk.source_file,
            "page_id": matched_chunk.page_id,
            "sdk_version": matched_chunk.sdk_version,
            "page_number": matched_chunk.page_number,
            "is_exact_token": spec["is_exact_token"],
            "text_snippet": matched_chunk.text[:150]
        })

    golden_set_file = WEEK4_DIR / "golden_set.json"
    golden_set_file.write_text(json.dumps(golden_set, indent=2), encoding="utf-8")
    print(f"\nSUCCESS: Generated {golden_set_file} with 12 mapped ground-truth questions!")
    for item in golden_set:
        print(f" [{item['id']}] {item['question']}\n      -> Target Chunk: {item['correct_chunk_id']} | File: {item['source_file']} (Version: {item['sdk_version']})")

if __name__ == "__main__":
    main()
