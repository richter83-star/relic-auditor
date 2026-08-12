def create_analysis(document):
    db.save(document)
    queue.add("analysis", document.id)
    return {"status": "queued"}
