import json
import html
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).parent
PORT = int(os.environ.get("PORT", "8000"))


def _words(text):
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _read_json(url, headers=None):
    request = urllib.request.Request(
        url,
        headers=headers
        or {"User-Agent": "LessonResearchTool/1.0 (educational use)"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        return json.load(response)


def _plain_text(value):
    return html.unescape(re.sub(r"<[^>]+>", "", value or "")).strip()


def research(title, objective):
    query = f"{title} {objective}"
    wiki_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": title,
            "format": "json",
            "srlimit": 4,
        }
    )
    sources = []
    notes = []
    errors = []
    images = []
    videos = []
    video_search = None
    topic_terms = {
        word for word in _words(title) if len(word) > 3 and word not in {
            "about", "after", "before", "from", "into", "lesson", "through", "with"
        }
    }
    try:
        results = _read_json(wiki_url)["query"]["search"]
        if not results:
            errors.append(f"Website search returned no matches for: {title}.")
        for result in results:
            page_title = result["title"]
            page_url = "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
                page_title.replace(" ", "_")
            )
            snippet = re.sub(r"<[^>]+>", "", result.get("snippet", ""))
            sources.append(
                {"kind": "Website", "title": page_title, "url": page_url}
            )
            notes.append(f"{page_title}: {snippet}")
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        errors.append(f"Website search unavailable: {exc}")

    image_url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": title,
            "gsrnamespace": 6,
            "gsrlimit": 4,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": 900,
            "format": "json",
        }
    )
    try:
        pages = _read_json(
            image_url,
            headers={"User-Agent": "LessonResearchTool/1.0 (educational use)"},
        ).get("query", {}).get("pages", {})
        for page in sorted(pages.values(), key=lambda item: item.get("index", 999)):
            image_info = (page.get("imageinfo") or [{}])[0]
            metadata = image_info.get("extmetadata", {})
            mime_type = image_info.get("mime", "")
            thumbnail = image_info.get("thumburl")
            file_page = image_info.get("descriptionurl")
            license_name = _plain_text(
                metadata.get("LicenseShortName", {}).get("value", "")
            )
            if (
                not mime_type.startswith("image/")
                or not thumbnail
                or not file_page
                or not license_name
                or not thumbnail.startswith("https://")
                or not file_page.startswith("https://commons.wikimedia.org/")
            ):
                continue
            image_title = page.get("title", "Educational image")
            if image_title.startswith("File:"):
                image_title = image_title[5:]
            image_title = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", image_title)
            description = _plain_text(
                metadata.get("ImageDescription", {}).get("value", "")
            )
            artist = _plain_text(metadata.get("Artist", {}).get("value", ""))
            images.append(
                {
                    "title": image_title,
                    "url": thumbnail,
                    "page_url": file_page,
                    "alt": (description or image_title)[:400],
                    "license": license_name,
                    "artist": artist,
                }
            )
        if not images:
            errors.append(
                f"No licensed image results were found for: {title}. The lesson can still be generated."
            )
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        errors.append(f"Image search unavailable; the lesson can still be generated: {exc}")

    video_url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"{title} video",
            "gsrnamespace": 6,
            "gsrlimit": 8,
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|mime",
            "iiurlwidth": 700,
            "format": "json",
        }
    )
    try:
        pages = _read_json(
            video_url,
            headers={"User-Agent": "LessonResearchTool/1.0 (educational use)"},
        ).get("query", {}).get("pages", {})
        for page in sorted(pages.values(), key=lambda item: item.get("index", 999)):
            image_info = (page.get("imageinfo") or [{}])[0]
            metadata = image_info.get("extmetadata", {})
            video_mime = image_info.get("mime", "")
            media_url = image_info.get("url")
            file_page = image_info.get("descriptionurl")
            license_name = _plain_text(
                metadata.get("LicenseShortName", {}).get("value", "")
            )
            if (
                not video_mime.startswith("video/")
                or not media_url
                or not media_url.startswith("https://upload.wikimedia.org/")
                or not file_page
                or not file_page.startswith("https://commons.wikimedia.org/")
                or not license_name
            ):
                continue
            video_title = page.get("title", "Educational video")
            if video_title.startswith("File:"):
                video_title = video_title[5:]
            video_title = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", video_title)
            description = _plain_text(
                metadata.get("ImageDescription", {}).get("value", "")
            )
            if topic_terms and not topic_terms.intersection(
                _words(video_title + " " + description)
            ):
                continue
            video = {
                "title": video_title,
                "url": media_url,
                "page_url": file_page,
                "mime": video_mime,
                "thumbnail": image_info.get("thumburl", ""),
                "license": license_name,
                "artist": _plain_text(metadata.get("Artist", {}).get("value", "")),
                "alt": description[:400],
                "provider": "Wikimedia Commons",
            }
            videos.append(video)
            sources.append(
                {
                    "kind": "Video",
                    "title": video_title,
                    "url": file_page,
                }
            )
            if len(videos) == 3:
                break
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        errors.append(f"Open video search unavailable: {exc}")

    encoded = urllib.parse.quote_plus(query)
    sources.append(
        {
            "kind": "Book search",
            "title": f"Books about {title}",
            "url": f"https://books.google.com/books?q={encoded}",
        }
    )
    sources.append(
        {
            "kind": "Book search",
            "title": f"Open Library books about {title}",
            "url": f"https://openlibrary.org/search?q={encoded}",
        }
    )
    books_url = "https://www.googleapis.com/books/v1/volumes?" + urllib.parse.urlencode(
        {"q": query, "maxResults": 3, "printType": "books"}
    )
    try:
        books = _read_json(books_url).get("items", [])
        for book in books:
            info = book.get("volumeInfo", {})
            book_title = info.get("title", "Untitled book")
            authors = ", ".join(info.get("authors", []))
            sources.append(
                {
                    "kind": "Book",
                    "title": book_title + (f" — {authors}" if authors else ""),
                    "url": info.get(
                        "infoLink",
                        f"https://books.google.com/books?id={urllib.parse.quote(book.get('id', ''))}",
                    ),
                }
            )
            description = re.sub(r"<[^>]+>", "", info.get("description", ""))
            if description:
                notes.append(
                    f"Book catalog description for {book_title}: {description[:500]}"
                )
    except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
        errors.append(f"Google Books catalog unavailable; trying Open Library: {exc}")
        try:
            open_library_url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(
                {
                    "title": title,
                    "limit": 3,
                    "fields": "key,title,author_name,first_publish_year,first_sentence",
                }
            )
            books = _read_json(open_library_url).get("docs", [])
            if not books:
                errors.append(f"Open Library found no book records for: {title}.")
            for book in books:
                book_title = book.get("title", "Untitled book")
                authors = ", ".join(book.get("author_name", []))
                book_key = book.get("key")
                if book_key:
                    sources.append(
                        {
                            "kind": "Book",
                            "title": book_title + (f" — {authors}" if authors else ""),
                            "url": "https://openlibrary.org" + book_key,
                        }
                    )
                first_sentence = book.get("first_sentence", [])
                if isinstance(first_sentence, list) and first_sentence:
                    notes.append(
                        f"Open Library catalog excerpt for {book_title}: {first_sentence[0]}"
                    )
        except (OSError, ValueError, KeyError, urllib.error.URLError) as fallback_exc:
            errors.append(f"Book catalog search unavailable: {fallback_exc}")

    youtube_key = os.environ.get("YOUTUBE_API_KEY")
    if youtube_key:
        youtube_url = "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(
            {
                "part": "snippet",
                "type": "video",
                "maxResults": 3,
                "q": query,
                "key": youtube_key,
            }
        )
        try:
            youtube_results = _read_json(youtube_url).get("items", [])
            for video in youtube_results:
                snippet = video.get("snippet", {})
                video_id = video.get("id", {}).get("videoId")
                if not video_id:
                    continue
                video_title = snippet.get("title", "Untitled video")
                thumbnails = snippet.get("thumbnails", {})
                thumbnail = (
                    thumbnails.get("high")
                    or thumbnails.get("medium")
                    or thumbnails.get("default")
                    or {}
                )
                if topic_terms and not topic_terms.intersection(
                    _words(video_title + " " + snippet.get("description", ""))
                ):
                    continue
                sources.append(
                    {
                        "kind": "YouTube video",
                        "title": f"{video_title} — {snippet.get('channelTitle', 'YouTube')}",
                        "url": f"https://www.youtube.com/watch?v={urllib.parse.quote(video_id)}",
                    }
                )
                videos.append(
                    {
                        "title": video_title,
                        "url": f"https://www.youtube-nocookie.com/embed/{urllib.parse.quote(video_id)}",
                        "page_url": f"https://www.youtube.com/watch?v={urllib.parse.quote(video_id)}",
                        "mime": "video/youtube",
                        "thumbnail": thumbnail.get("url", ""),
                        "license": "YouTube",
                        "artist": snippet.get("channelTitle", ""),
                        "alt": video_title,
                        "provider": "YouTube",
                    }
                )
                notes.append(
                    f"YouTube video description for {video_title}: "
                    f"{re.sub(r'<[^>]+>', '', snippet.get('description', ''))[:300]}"
                )
        except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
            errors.append(f"YouTube video search unavailable: {exc}")
    else:
        errors.append("YouTube API key not configured; searching for openly licensed videos instead.")
        sources.append(
            {
                "kind": "YouTube search",
                "title": f"Video lessons about {title} — choose and review a specific video",
                "url": f"https://www.youtube.com/results?search_query={encoded}",
            }
        )
    if not videos:
        video_search = {
            "title": f"Video lessons about {title}",
            "url": f"https://www.youtube.com/results?search_query={encoded}",
        }
        errors.append(
            "No embeddable video was found; a topic-specific YouTube search link is available."
        )
    if _words(query) & {"http", "request", "response", "status", "web"}:
        sources.extend(
            [
                {
                    "kind": "Primary source",
                    "title": "HTTP Semantics (RFC 9110)",
                    "url": "https://www.rfc-editor.org/rfc/rfc9110.html",
                },
                {
                    "kind": "Reference",
                    "title": "MDN: HTTP response status codes",
                    "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status",
                },
                {
                    "kind": "Reference",
                    "title": "MDN: HTTP request methods",
                    "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Methods",
                },
            ]
        )
    if _words(query) & {"photosynthesis", "plant", "plants", "chlorophyll"}:
        sources.extend(
            [
                {
                    "kind": "Textbook",
                    "title": "OpenStax Biology 2e Section 8.2: Light-Dependent Reactions",
                    "url": "https://openstax.org/books/biology-2e/pages/8-2-the-light-dependent-reactions-of-photosynthesis",
                },
                {
                    "kind": "Reference",
                    "title": "Wikipedia: Calvin cycle (secondary overview)",
                    "url": "https://en.wikipedia.org/wiki/Calvin_cycle",
                },
            ]
        )
    return {
        "sources": sources,
        "research_notes": notes,
        "research_errors": errors,
        "images": images,
        "videos": videos,
        "video_search": video_search,
        "query": query,
    }


def make_lesson(title, objective, research_result):
    title = title.strip()
    objective = objective.strip()
    if not title or not objective:
        raise ValueError("Enter both a lesson title and a learning objective.")

    notes = research_result.get("research_notes", [])
    source_context = (
        "Research notes to check: " + " ".join(notes[:3])
        if notes
        else "Use the linked sources to verify details before teaching."
    )
    is_http = bool(
        _words(title + " " + objective)
        & {"http", "request", "response", "status"}
    )
    if is_http:
        content = f"""# {title}

**Learning objective:** {objective}

**45-minute lesson plan:** 5 min warm-up · 10 min explanation · 8 min worked example · 10 min practice · 7 min knowledge check · 5 min recap

## 1. Start here (5 min)
Think of a browser asking a server for a page. HTTP is a request/response protocol: the client sends a request and the server returns a response. Ask learners what information a response needs besides its body.

## 2. Key ideas (10 min)
- **GET** asks for a representation of a resource. It is defined as a safe, idempotent method; clients should not use it to request a state-changing action. GET requests can still have side effects such as logging.
- **POST** asks the target resource to process the enclosed content according to that resource's semantics. It is commonly used to submit form data or create a subordinate resource; it is not inherently idempotent.
- A response has a status code. **2xx** means the request was successfully received, understood, and accepted. For example, 200 is OK and 201 is Created.
- **4xx** indicates an error the client appears to have made (for example 400 Bad Request or 404 Not Found). **5xx** indicates the server is aware it has erred or is unable to perform the request (for example 500 Internal Server Error or 503 Service Unavailable).
- These are category-level interpretations, not a diagnosis of every failure. Read the specific status, headers, and API documentation.

## 3. Worked example (8 min)
1. A browser requests `GET /courses/7`. The server finds the course and returns `200 OK` with its representation.
2. A learner submits `POST /enrollments` with course information. If enrollment is created, the server may return `201 Created`.
3. If `/courses/999` does not exist, `404 Not Found` is a 4xx response. If the service is temporarily unavailable, `503 Service Unavailable` is a 5xx response.
4. Ask: which response should prompt a client to check its request, and which might justify retrying later? Retry policy depends on the method, status, and application semantics.

## 4. Practice (10 min)
In pairs, classify each scenario as GET or POST and choose a plausible status category: (a) retrieve a public article, (b) submit a new comment, (c) request a missing page, (d) a service crashes while handling a valid request. Explain your reasoning; do not infer that every POST changes state or every GET returns 200.

## 5. Knowledge check (7 min)
1. Which method is intended to retrieve a representation: GET or POST?
2. What do the 2xx, 4xx, and 5xx status-code classes broadly communicate?
3. Classify 404 and 503. Give one reason a client might receive each.
4. Is POST guaranteed to be idempotent? Explain.

**Answer key:** 1. GET. 2. Success; apparent client error; server error/unable to fulfill. 3. 404 is 4xx (resource not found); 503 is 5xx (service unavailable). 4. No; repeated POSTs can have repeated effects unless the application provides deduplication or other guarantees.

## 6. Recap (5 min)
Have each learner explain the request/response exchange, distinguish GET from POST, and classify one 2xx, 4xx, and 5xx example. Revisit the learning objective and correct any confusion between status classes and exact causes.

## Research notes for instructor
{source_context}

## References and supplementary learning
Sources are research starting points, not a substitute for checking the specific HTTP specification and current API behavior. The YouTube link opens relevant video search results; preview and select an appropriate video before assigning it.
"""
    elif _words(title + " " + objective) & {"photosynthesis", "plant", "plants", "chlorophyll"}:
        content = f"""# {title}

**Learning objective:** {objective}

**45-minute lesson plan:** 5 min warm-up · 10 min explanation · 8 min worked example · 10 min practice · 7 min knowledge check · 5 min recap

## 1. Start here (5 min)
Ask learners where a growing plant gets most of the matter that becomes its biomass. Use the question to distinguish energy from matter: light supplies energy, while carbon dioxide and water supply atoms used to build sugars.

## 2. Key ideas (10 min)
- **Overall idea:** Photosynthesis converts light energy into chemical energy stored in organic molecules. A simplified net equation is carbon dioxide + water + light energy → carbohydrate + oxygen; the balanced equation for glucose is 6CO₂ + 6H₂O + light → C₆H₁₂O₆ + 6O₂.
- **Light-dependent reactions:** In the thylakoid membranes of chloroplasts, absorbed light energy drives reactions that produce ATP and NADPH. Water is split, releasing oxygen.
- **Calvin cycle:** In the stroma, the cycle uses carbon dioxide, ATP, and NADPH to produce G3P, a molecule cells can use to build sugars and other organic compounds. The cycle depends on products of the light-dependent reactions; it is not simply a reaction that occurs only at night.
- **Practical connection:** Photosynthesis supports most food webs and contributes oxygen to the atmosphere. Actual rates depend on factors such as light, carbon dioxide, temperature, and water availability.

## 3. Worked example (8 min)
Trace the matter and energy for a leaf in sunlight. Light energy is captured by pigments; water supplies electrons and hydrogen and releases oxygen; carbon dioxide supplies carbon; ATP and NADPH help power carbon fixation; carbon-containing products can then be used to build sugars. Ask learners to identify which input supplies the carbon in carbohydrate (CO₂) and which input's breakdown releases O₂ (water).

## 4. Practice (10 min)
In pairs, label a chloroplast diagram with thylakoid, stroma, light, water, oxygen, carbon dioxide, ATP/NADPH, and sugar-building products. Then predict how limiting water or light could affect photosynthesis, and explain why the prediction is conditional rather than a complete account of plant growth.

## 5. Knowledge check (7 min)
1. What is the role of light energy in photosynthesis?
2. Which molecule is split in the light-dependent reactions, and what gas is released?
3. Where does carbon dioxide enter the process, and what does the Calvin cycle produce directly?
4. Does the Calvin cycle require products made by light-dependent reactions?

**Answer key:** 1. It is converted into chemical energy carried by ATP and NADPH. 2. Water; oxygen. 3. Carbon dioxide is fixed in the Calvin cycle in the stroma; it produces G3P, used to build sugars and other molecules. 4. Yes, it uses ATP and NADPH.

## 6. Recap (5 min)
Have learners trace the path of light energy and the carbon in CO₂ through photosynthesis. Revisit the objective and clarify that the simplified equation summarizes a network of reactions.

## References and supplementary learning
"""
    else:
        content = f"""# {title}

**Learning objective:** {objective}

**45-minute lesson plan:** 5 min warm-up · 10 min explanation · 8 min worked example · 10 min practice · 7 min knowledge check · 5 min recap

## 1. Start here (5 min)
Introduce the problem this lesson addresses. Ask learners to share what they already know and connect the topic to a real situation they recognize.

## 2. Key ideas (10 min)
- **Define the central idea:** Explain the most important term in plain language, then distinguish it from a commonly confused idea.
- **Explain the process:** Break the topic into a small number of logical steps. State when each step is useful and what evidence supports it.
- **Connect to the objective:** Learners should be able to demonstrate the action described in the learning objective by the end.
- **Check accuracy:** {source_context}

## 3. Worked example (8 min)
Model one realistic example aloud. Identify the starting conditions, apply the key ideas step by step, and explain why the result follows. Invite learners to predict the next step before revealing it.

## 4. Practice (10 min)
Learners work individually or in pairs on a new scenario that requires applying the same ideas. Ask them to justify their approach and compare answers. Instructor: address misconceptions using the sources below.

## 5. Knowledge check (7 min)
1. In your own words, explain the central idea in this lesson.
2. Apply it to a new example and describe your reasoning.
3. What is one limitation or misconception to watch for?

**Answer key:** Look for an accurate explanation grounded in the cited sources, a reasoned application to the new scenario, and recognition that context may affect the answer.

## 6. Recap (5 min)
Return to the learning objective. Ask learners to summarize one key idea and one practical application, then identify what they would verify before applying it in a new context.

## References and supplementary learning
Search links are starting points: verify a specific book, web page, or video before recommending it.
"""
    references = research_result.get("sources", [])
    images = research_result.get("images", [])
    if images:
        content += "\n## Photo resources\n\n"
        content += "\n\n".join(
            f"![{image['alt']}]({image['url']})\n\n"
            f"*{image['title']}. "
            f"[Image and attribution]({image['page_url']}) · "
            f"{image['license']}"
            + (f" · {image['artist']}" if image.get("artist") else "")
            + "*"
            for image in images
        )
        content += "\n\n"
    videos = research_result.get("videos", [])
    video_search = research_result.get("video_search")
    if videos or video_search:
        content += "\n## Video resources\n\n"
        content += "*Supplementary and optional; video viewing is outside the 45-minute lesson plan.*\n\n"
        for video in videos:
            credit = " · ".join(
                item for item in (video.get("license"), video.get("artist")) if item
            )
            content += (
                f"- **[▶ {video['title']}]({video['page_url']})**"
                + (f" — {credit}" if credit else "")
                + "\n"
            )
        if video_search:
            content += (
                f"- [Search YouTube for {title}]({video_search['url']}) "
                "(search results; select and review a specific video before assigning.)\n"
            )
        content += "\n"
    content += "\n" + "\n".join(
        f"- **[{item['kind']}: {item['title']}]({item['url']})**"
        for item in references
    )
    return content


def bold_reference_links(content):
    in_references = False
    formatted = []
    for line in content.splitlines():
        if re.match(r"^#{1,3}\s*(references|sources)\b", line, re.IGNORECASE):
            in_references = True
        elif in_references and re.match(r"^#{1,3}\s+", line):
            in_references = False
        if in_references and re.match(r"^\s*[-*]\s+", line) and "](" in line:
            line = re.sub(
                r"(?<!\*)\[([^\]]+)\]\((https?://[^)]+)\)(?!\*)",
                r"**[\1](\2)**",
                line,
            )
        formatted.append(line)
    return "\n".join(formatted)


def generate_with_model(title, objective, research_result):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return make_lesson(title, objective, research_result), "grounded local generator"
    sources = research_result.get("sources", [])
    prompt = (
        "Create an accurate, engaging lesson in Markdown for an instructor. "
        "It must satisfy the exact learning objective, include explanations, a worked example, "
        "an active practical activity, and a knowledge check with answer key. Include a schedule "
        "whose components total exactly 45 minutes. Keep claims within the supplied research; "
        "do not invent citations or references. Add a short instructor verification note. "
        "End with the supplied reference links and label YouTube search links as search results. "
        "Use concise, learner-friendly language.\n\n"
        f"Lesson title: {title}\nLearning objective: {objective}\n"
        f"Research notes: {research_result.get('research_notes', [])}\n"
        f"Verified reference links: {json.dumps(sources, ensure_ascii=False)}"
    )
    payload = json.dumps(
        {
            "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": [
                {
                    "role": "system",
                    "content": "You are a careful educational content researcher. Do not fabricate facts or sources.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    content = result["choices"][0]["message"]["content"]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("The configured AI provider returned an empty lesson.")
    content = add_photo_resources(content.strip(), research_result.get("images", []))
    content = add_video_resources(
        content,
        research_result.get("videos", []),
        research_result.get("video_search"),
        title,
    )
    return bold_reference_links(content.strip()), os.environ.get(
        "OPENAI_MODEL", "gpt-4o-mini"
    )


def add_photo_resources(content, images):
    if not images or re.search(r"^#{1,3}\s+photo resources\b", content, re.IGNORECASE | re.MULTILINE):
        return content
    section = "## Photo resources\n\n" + "\n\n".join(
        f"![{image['alt']}]({image['url']})\n\n"
        f"*{image['title']}. "
        f"[Image and attribution]({image['page_url']}) · "
        f"{image['license']}"
        + (f" · {image['artist']}" if image.get("artist") else "")
        + "*"
        for image in images
    )
    references = re.search(r"^#{1,3}\s+(references|sources)\b", content, re.IGNORECASE | re.MULTILINE)
    if references:
        return content[:references.start()].rstrip() + "\n\n" + section + "\n\n" + content[references.start():]
    return content.rstrip() + "\n\n" + section


def add_video_resources(content, videos, video_search, title):
    if not videos and not video_search:
        return content
    if re.search(r"^#{1,3}\s+video resources\b", content, re.IGNORECASE | re.MULTILINE):
        return content
    section = (
        "## Video resources\n\n"
        "*Supplementary and optional; video viewing is outside the 45-minute lesson plan.*\n\n"
    )
    for video in videos:
        credit = " · ".join(
            item for item in (video.get("license"), video.get("artist")) if item
        )
        section += (
            f"- **[▶ {video['title']}]({video['page_url']})**"
            + (f" — {credit}" if credit else "")
            + "\n"
        )
    if video_search:
        section += (
            f"- [Search YouTube for {title}]({video_search['url']}) "
            "(search results; select and review a specific video before assigning.)\n"
        )
    return content.rstrip() + "\n\n" + section.rstrip()


def qc_research(content, sources, research_notes=None):
    issues = []
    if not sources:
        issues.append(
            {
                "severity": "High",
                "issue": "No sources were retrieved or attached.",
                "recommendation": "Retry research and verify claims against primary sources before teaching.",
            }
        )
    elif not any(source["kind"] in {"Primary source", "Reference"} for source in sources):
        issues.append(
            {
                "severity": "Medium",
                "issue": "The references do not include a clearly authoritative primary source.",
                "recommendation": "Add a specification, textbook, or authoritative institutional source.",
            }
        )
    if not research_notes:
        issues.append(
            {
                "severity": "Medium",
                "issue": "No retrieved research excerpts are available for claim-by-claim corroboration.",
                "recommendation": "Review lesson claims against the linked source text and add inline citations.",
            }
        )
    issues.append(
        {
            "severity": "Low",
            "issue": "Automated QC does not establish that every factual claim is correct.",
            "recommendation": "Have an instructor verify key claims against the cited primary references before teaching.",
        }
    )
    if "2xx" in content and not all(code in content for code in ("4xx", "5xx")):
        issues.append(
            {
                "severity": "High",
                "issue": "Status-code classes are not all covered consistently.",
                "recommendation": "Verify every status category and add representative examples.",
            }
        )
    return {
        "layer": "Research and factual accuracy",
        "status": "Review recommended" if issues else "Passed automated checks",
        "issues": issues,
        "note": "Automated checks cannot prove factual correctness; instructor source verification is required.",
    }


def qc_instruction(content, title, objective):
    issues = []
    if not title.strip() or not objective.strip():
        issues.append(
            {
                "severity": "High",
                "issue": "A lesson title or learning objective is missing.",
                "recommendation": "Enter a focused title and measurable learning objective.",
            }
        )
    if "45-minute lesson plan" not in content:
        issues.append(
            {
                "severity": "High",
                "issue": "The lesson has no explicit 45-minute schedule.",
                "recommendation": "Add a timed plan that totals 45 minutes.",
            }
        )
    if not all(section in content for section in ("Worked example", "Practice", "Knowledge check")):
        issues.append(
            {
                "severity": "Medium",
                "issue": "An example, practice activity, or knowledge check is missing.",
                "recommendation": "Add an example, an active practice task, and a check for understanding.",
            }
        )
    overlap = _words(objective) & _words(content)
    meaningful = _words(objective) - {"explain", "describe", "identify", "understand", "and", "the", "of", "to", "a", "an"}
    if meaningful and len(overlap & meaningful) / len(meaningful) < 0.35:
        issues.append(
            {
                "severity": "Medium",
                "issue": "Objective wording has limited overlap with lesson content; alignment needs instructor review.",
                "recommendation": "Map each objective verb and concept to a specific explanation, activity, and assessment item.",
            }
        )
    return {
        "layer": "Instructional quality",
        "status": "Review recommended" if issues else "Passed automated checks",
        "issues": issues,
        "note": "Alignment and suitability are heuristic checks; review the lesson for your learners.",
    }


class Handler(BaseHTTPRequestHandler):
    def _json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/styles.css":
            body = (ROOT / "styles.css").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/app.js":
            body = (ROOT / "app.js").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/dashboard-illustration.svg":
            body = (ROOT / "dashboard-illustration.svg").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            title = data.get("title", "").strip()
            objective = data.get("objective", "").strip()
            if not title or not objective:
                self._json({"error": "Enter both a lesson title and a learning objective."}, 400)
                return
            if self.path == "/api/research":
                self._json(research(title, objective))
            elif self.path == "/api/generate":
                research_result = data.get("research") or research(title, objective)
                content, mode = generate_with_model(title, objective, research_result)
                self._json(
                    {
                        "content": content,
                        "qc_research": qc_research(
                            content,
                            research_result["sources"],
                            research_result.get("research_notes", []),
                        ),
                        "qc_instruction": qc_instruction(content, title, objective),
                        "sources": research_result["sources"],
                        "images": research_result.get("images", []),
                        "videos": research_result.get("videos", []),
                        "video_search": research_result.get("video_search"),
                        "mode": mode,
                    }
                )
            elif self.path == "/api/qc":
                content = data.get("content", "")
                sources = data.get("sources", [])
                if not content.strip():
                    self._json({"error": "Generate or enter lesson content before running QC."}, 400)
                    return
                self._json(
                    {
                        "qc_research": qc_research(
                            content, sources, data.get("research_notes", [])
                        ),
                        "qc_instruction": qc_instruction(content, title, objective),
                    }
                )
            else:
                self._json({"error": "Not found"}, 404)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:
            self._json({"error": f"Generation failed: {exc}"}, 500)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    print(f"Lesson Research Tool running at http://localhost:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
