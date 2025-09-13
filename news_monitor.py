#!/usr/bin/env python3
import feedparser
import requests
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import re
import time

# Try to import dateutil, fallback if not available
try:
    from dateutil import parser as date_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

def analyze_article_with_groq(title, summary, max_retries=3):
    """Use Groq (free Llama) to analyze and score articles"""
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        print("⚠️ GROQ_API_KEY not set, skipping AI analysis")
        return None
    
    prompt = f"""Analyze this news article about China policy and provide a JSON response with:
1. relevance_score (0-10): How relevant to China policy/geopolitics
2. importance_score (0-10): How important/impactful this news is
3. category: One of ["Trade", "Technology", "Geopolitics", "Economy", "Military", "Diplomacy", "Other"]
4. key_points: List of 3-5 main points (max 20 words each)
5. summary_one_line: One sentence summary (max 30 words)

Title: {title}
Content: {summary[:1000]}

Respond only with valid JSON:"""

    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.1-8b-instant",  # Free tier
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 500
                },
                timeout=10
            )
            
            if response.status_code == 200:
                ai_response = response.json()['choices'][0]['message']['content']
                
                # Try to parse JSON
                try:
                    return json.loads(ai_response)
                except json.JSONDecodeError:
                    # Extract JSON from response if wrapped in markdown
                    json_match = re.search(r'```json\n(.*?)\n```', ai_response, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group(1))
                    else:
                        # Try to find JSON in the response
                        json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                        if json_match:
                            return json.loads(json_match.group(0))
                
        except Exception as e:
            print(f"Groq API attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait before retry
    
    return None

def analyze_article_with_huggingface(title, summary):
    """Use Hugging Face Inference API (free tier)"""
    api_key = os.environ.get('HUGGINGFACE_API_KEY')
    if not api_key:
        return None
    
    try:
        # Use a classification model
        response = requests.post(
            "https://api-inference.huggingface.co/models/facebook/bart-large-mnli",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "inputs": f"{title}. {summary[:500]}",
                "parameters": {
                    "candidate_labels": [
                        "highly important international politics",
                        "trade and economics",
                        "technology and innovation", 
                        "military and security",
                        "diplomatic relations",
                        "routine news"
                    ]
                }
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            # Convert to our scoring system
            top_label = result['labels'][0]
            score = result['scores'][0]
            
            importance_map = {
                "highly important international politics": 9,
                "military and security": 8,
                "trade and economics": 7,
                "technology and innovation": 7,
                "diplomatic relations": 6,
                "routine news": 4
            }
            
            return {
                "relevance_score": min(10, int(score * 10) + 3),
                "importance_score": importance_map.get(top_label, 5),
                "category": top_label.replace("highly important ", "").title(),
                "confidence": score
            }
            
    except Exception as e:
        print(f"HuggingFace API failed: {e}")
    
    return None

def analyze_article_with_ollama(title, summary):
    """Use local Ollama if available (completely free)"""
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.2:1b",  # Lightweight model
                "prompt": f"""Rate this China-related news article from 1-10 for:
1. Political importance
2. Economic impact  
3. Global relevance

Title: {title}
Summary: {summary[:800]}

Respond with only: importance=X, economic=Y, global=Z (numbers only)""",
                "stream": False,
                "options": {"temperature": 0.1}
            },
            timeout=15
        )
        
        if response.status_code == 200:
            text = response.json()['response']
            
            # Parse scores
            scores = {}
            for match in re.finditer(r'(\w+)=(\d+)', text):
                scores[match.group(1)] = int(match.group(2))
            
            if scores:
                avg_score = sum(scores.values()) / len(scores)
                return {
                    "relevance_score": min(10, max(1, avg_score)),
                    "importance_score": scores.get('importance', 5),
                    "source": "ollama_local"
                }
                
    except requests.exceptions.ConnectionError:
        # Ollama not running locally
        pass
    except Exception as e:
        print(f"Ollama failed: {e}")
    
    return None

def get_ai_analysis(title, summary):
    """Try multiple AI services in order of preference"""
    
    # 1. Try Groq first (best free option)
    analysis = analyze_article_with_groq(title, summary)
    if analysis:
        analysis['ai_source'] = 'groq'
        return analysis
    
    # 2. Try Ollama (local, completely free)
    analysis = analyze_article_with_ollama(title, summary)
    if analysis:
        analysis['ai_source'] = 'ollama'
        return analysis
    
    # 3. Try HuggingFace (good free tier)
    analysis = analyze_article_with_huggingface(title, summary)
    if analysis:
        analysis['ai_source'] = 'huggingface'
        return analysis
    
    # 4. Fallback to rule-based scoring
    return get_rule_based_score(title, summary)

def get_rule_based_score(title, summary):
    """Fallback rule-based scoring when AI is unavailable"""
    text = f"{title} {summary}".lower()
    
    # High importance keywords
    high_keywords = ['war', 'conflict', 'sanctions', 'trade war', 'military', 'nuclear', 'crisis']
    medium_keywords = ['policy', 'agreement', 'meeting', 'summit', 'negotiate', 'deal']
    
    high_score = sum(2 for keyword in high_keywords if keyword in text)
    medium_score = sum(1 for keyword in medium_keywords if keyword in text)
    
    base_score = 5
    importance = min(10, base_score + high_score + medium_score)
    
    # Determine category
    if any(kw in text for kw in ['trade', 'tariff', 'export', 'import']):
        category = "Trade"
    elif any(kw in text for kw in ['military', 'defense', 'weapon']):
        category = "Military"
    elif any(kw in text for kw in ['tech', 'ai', 'chip', 'semiconductor']):
        category = "Technology"
    else:
        category = "Other"
    
    return {
        "relevance_score": importance,
        "importance_score": importance,
        "category": category,
        "ai_source": "rule_based"
    }

def load_processed_articles():
    """Load the list of already processed articles"""
    try:
        with open('processed_articles.json', 'r') as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_processed_articles(processed_articles):
    """Save the list of processed articles"""
    try:
        with open('processed_articles.json', 'w') as f:
            json.dump(list(processed_articles), f, indent=2)
    except Exception as e:
        print(f"Error saving processed articles: {e}")

def fetch_full_article_content(url, max_chars=2000):
    """Attempt to fetch fuller article content from URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        
        # Simple text extraction (basic approach)
        text = response.text
        
        # Remove HTML tags and get clean text
        import re
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        
        # Try to find article content (look for common patterns)
        paragraphs = []
        lines = text.split('.')
        for line in lines:
            line = line.strip()
            if len(line) > 100 and not any(skip in line.lower() for skip in 
                ['cookie', 'subscribe', 'newsletter', 'advertisement', 'javascript']):
                paragraphs.append(line)
        
        content = '. '.join(paragraphs[:10])  # Take first 10 meaningful sentences
        return content[:max_chars] if content else None
        
    except Exception as e:
        print(f"Could not fetch full content from {url}: {e}")
        return None

def fetch_news():
    """Fetch news from multiple RSS feeds with enhanced diversity"""
    feeds = [
        # Major international news sources - diversified endpoints
        ('Reuters World', 'https://feeds.reuters.com/reuters/worldNews'),
        ('Reuters Business', 'https://feeds.reuters.com/reuters/businessNews'),
        ('BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml'),
        ('BBC Asia', 'https://feeds.bbci.co.uk/news/world/asia/rss.xml'),
        ('CNN International', 'https://rss.cnn.com/rss/cnn_world.rss'),
        ('AP News International', 'https://feeds.apnews.com/apnews/World'),
        
        # Business & Economic sources
        ('Financial Times World', 'https://www.ft.com/world?format=rss'),
        ('Wall Street Journal World', 'https://feeds.a.dj.com/rss/RSSWorldNews.xml'),
        ('Bloomberg Politics', 'https://feeds.bloomberg.com/politics/news.rss'),
        ('Economic Times World', 'https://economictimes.indiatimes.com/news/international/world-news/rssfeeds/2563.cms'),
        
        # Asia-Pacific focused
        ('South China Morning Post', 'https://www.scmp.com/rss/91/feed'),
        ('Japan Times', 'https://www.japantimes.co.jp/feed/topstories/'),
        ('Straits Times Asia', 'https://www.straitstimes.com/news/asia/rss.xml'),
        ('Nikkei Asia', 'https://asia.nikkei.com/rss/feed/nar'),
        
        # Alternative sources for better diversity
        ('Foreign Affairs', 'https://www.foreignaffairs.com/rss.xml'),
        ('Politico', 'https://www.politico.com/rss/politics08.xml'),
        ('The Guardian World', 'https://www.theguardian.com/world/rss'),
        ('NPR World', 'https://feeds.npr.org/1004/feed.json'),
    ]
    
    all_articles = []
    cutoff_date = datetime.now() - timedelta(hours=24)  # Exactly 24 hours
    
    # Limit articles per source to ensure diversity
    max_articles_per_source = 3
    
    for source_name, feed_url in feeds:
        try:
            print(f"Fetching from {source_name}...")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/rss+xml, application/xml, text/xml'
            }
            
            response = requests.get(feed_url, headers=headers, timeout=15)
            feed = feedparser.parse(response.content)
            
            recent_count = 0
            articles_from_source = 0
            
            for entry in feed.entries:
                if articles_from_source >= max_articles_per_source:
                    break
                    
                # Parse publication date more robustly
                pub_date = None
                
                # Try multiple date fields
                for date_field in ['published_parsed', 'updated_parsed', 'created_parsed']:
                    if hasattr(entry, date_field) and getattr(entry, date_field):
                        try:
                            pub_date = datetime(*getattr(entry, date_field)[:6])
                            break
                        except:
                            continue
                
                # If no parsed date, try string dates
                if not pub_date and HAS_DATEUTIL:
                    for date_field in ['published', 'updated', 'created']:
                        if hasattr(entry, date_field):
                            try:
                                pub_date = date_parser.parse(getattr(entry, date_field))
                                break
                            except:
                                continue
                
                # Only include articles from last 24 hours
                if pub_date and pub_date >= cutoff_date:
                    recent_count += 1
                    articles_from_source += 1
                    
                    # Get article summary/content
                    summary = entry.get('summary', entry.get('description', ''))
                    
                    # Try to get fuller content for better preview
                    full_content = fetch_full_article_content(entry.get('link', ''))
                    if full_content and len(full_content) > len(summary):
                        summary = full_content
                    
                    article = {
                        'title': entry.get('title', ''),
                        'link': entry.get('link', ''),
                        'summary': summary,
                        'published': pub_date.strftime('%Y-%m-%d %H:%M UTC'),
                        'source': source_name,
                        'hours_ago': int((datetime.now() - pub_date).total_seconds() / 3600)
                    }
                    all_articles.append(article)
            
            print(f"Found {recent_count} recent articles from {source_name} (took {articles_from_source})")
            
        except Exception as e:
            print(f"Error fetching {source_name}: {e}")
    
    # Sort by publication date (newest first) and ensure source diversity
    all_articles.sort(key=lambda x: x['published'], reverse=True)
    
    # Ensure source diversity by limiting consecutive articles from same source
    diversified_articles = []
    source_counts = {}
    
    for article in all_articles:
        source = article['source']
        if source_counts.get(source, 0) < 2 or len(diversified_articles) < 5:
            diversified_articles.append(article)
            source_counts[source] = source_counts.get(source, 0) + 1
    
    return diversified_articles

def is_china_policy_related(title, summary):
    """Enhanced function to check if article is China policy-related"""
    text = f"{title} {summary}".lower()
    
    # Primary China keywords - must have at least one
    china_keywords = [
        'china', 'chinese', 'beijing', 'shanghai', 'guangzhou', 'shenzhen',
        'xi jinping', 'ccp', 'communist party', 'prc', 'peoples republic',
        'mainland china', 'sino-'
    ]
    
    # Policy/Economic keywords - must have at least one if China keyword present
    policy_keywords = [
        # Trade & Economics
        'trade', 'tariff', 'import', 'export', 'economy', 'economic', 'gdp',
        'investment', 'market', 'stock', 'yuan', 'renminbi', 'currency',
        'inflation', 'growth', 'manufacturing', 'supply chain',
        
        # Technology & Innovation
        'technology', 'tech', 'semiconductor', 'chip', 'ai', 'artificial intelligence',
        'huawei', 'tencent', 'alibaba', 'baidu', 'bytedance', 'tiktok',
        'electric vehicle', 'ev', 'battery', 'solar', 'renewable',
        
        # Geopolitics & International Relations
        'policy', 'diplomacy', 'diplomatic', 'foreign policy', 'sanctions',
        'biden', 'trump', 'us-china', 'america', 'european union', 'nato',
        'g7', 'g20', 'wto', 'world bank', 'imf',
        
        # Regional Issues
        'taiwan', 'hong kong', 'macau', 'tibet', 'xinjiang', 'uighur', 'uyghur',
        'south china sea', 'east china sea', 'belt and road', 'bri',
        
        # Governance & Society
        'government', 'regulation', 'law', 'legal', 'court', 'human rights',
        'democracy', 'protest', 'covid', 'pandemic', 'lockdown', 'zero covid',
        'environment', 'climate', 'carbon', 'emission', 'pollution'
    ]
    
    # Check if has China keyword
    has_china = any(keyword in text for keyword in china_keywords)
    
    # Check if has policy keyword
    has_policy = any(keyword in text for keyword in policy_keywords)
    
    # Also check for US-China or other country-China relations
    country_china_patterns = [
        r'\bus[\s\-]china\b', r'\bchina[\s\-]us\b',
        r'\beurope[\s\-]china\b', r'\bchina[\s\-]europe\b',
        r'\bindia[\s\-]china\b', r'\bchina[\s\-]india\b',
        r'\bjapan[\s\-]china\b', r'\bchina[\s\-]japan\b'
    ]
    
    has_relation = any(re.search(pattern, text) for pattern in country_china_patterns)
    
    return has_china and (has_policy or has_relation)

def filter_and_analyze_articles(articles):
    """Filter articles and add AI analysis"""
    filtered_articles = []
    
    print("\n🤖 AI-analyzing articles for China policy relevance and importance...")
    
    for article in articles:
        if is_china_policy_related(article['title'], article['summary']):
            print(f"🔍 Analyzing: {article['title'][:60]}...")
            
            # Get AI analysis
            ai_analysis = get_ai_analysis(article['title'], article['summary'])
            
            if ai_analysis:
                article.update(ai_analysis)
                print(f"   ✓ Score: {ai_analysis.get('importance_score', 0)}/10 | "
                      f"Category: {ai_analysis.get('category', 'Unknown')} | "
                      f"AI: {ai_analysis.get('ai_source', 'unknown')}")
            else:
                article.update(get_rule_based_score(article['title'], article['summary']))
                print(f"   ✓ Score: {article.get('importance_score', 0)}/10 (rule-based)")
            
            filtered_articles.append(article)
    
    # Sort by AI-determined importance
    filtered_articles.sort(key=lambda x: (
        x.get('importance_score', 0) * 0.6 +  # 60% importance
        x.get('relevance_score', 0) * 0.4      # 40% relevance
    ), reverse=True)
    
    return filtered_articles

def send_email(articles):
    """Send email with AI-sorted articles"""
    email_user = os.environ.get('EMAIL_USER')
    email_password = os.environ.get('EMAIL_PASSWORD')
    recipient_email = os.environ.get('RECIPIENT_EMAIL')
    
    if not all([email_user, email_password, recipient_email]):
        print("❌ Email credentials not configured")
        return
    
    # Create email content
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    if articles:
        # Count AI sources used
        ai_sources = {}
        for article in articles:
            source = article.get('ai_source', 'unknown')
            ai_sources[source] = ai_sources.get(source, 0) + 1
        
        ai_summary = " + ".join([f"{count} {source}" for source, count in ai_sources.items()])
        
        subject = f"🤖 AI-Sorted China Policy News - {len(articles)} articles - {current_date}"
        
        # HTML email body with AI enhancements
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto;">
            <h2 style="color: #d32f2f; text-align: center; border-bottom: 2px solid #d32f2f; padding-bottom: 10px;">
                🇨🇳🤖 AI-Sorted China Policy News
            </h2>
            <div style="text-align: center; color: #666; margin-bottom: 20px;">
                <p><strong>📅 Date:</strong> {current_date} | <strong>📊 Articles:</strong> {len(articles)}</p>
                <p style="font-size: 14px; color: #888;">
                    🤖 AI-Analyzed & Sorted • ⏰ Last 24 hours • 🌐 Multiple sources<br>
                    <strong>AI Processing:</strong> {ai_summary}
                </p>
            </div>
            <hr style="border: 1px solid #ddd; margin: 20px 0;">
        """
        
        # Group by category for better organization
        categories = {}
        for article in articles:
            cat = article.get('category', 'Other')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(article)
        
        # Sort categories by importance
        for category, cat_articles in sorted(categories.items(), 
                                           key=lambda x: max(a.get('importance_score', 0) for a in x[1]), 
                                           reverse=True):
            
            html_content += f"""
            <h3 style="color: #d32f2f; border-bottom: 1px solid #ddd; padding-bottom: 5px; margin-top: 25px;">
                📂 {category} ({len(cat_articles)} articles)
            </h3>
            """
            
            for i, article in enumerate(cat_articles, 1):
                # Show more content and AI scores
                summary_text = article['summary'][:800] + ('...' if len(article['summary']) > 800 else '')
                
                # Time and scoring info
                hours_ago = article.get('hours_ago', 0)
                time_indicator = f"🕐 {hours_ago}h ago" if hours_ago < 24 else f"📅 {article['published']}"
                
                importance = article.get('importance_score', 0)
                relevance = article.get('relevance_score', 0)
                ai_source = article.get('ai_source', 'unknown')
                
                # Score color coding
                score_color = "#ff4444" if importance >= 8 else "#ff8800" if importance >= 6 else "#666"
                
                html_content += f"""
                <div style="margin-bottom: 30px; padding: 20px; border-left: 4px solid {score_color}; background: #f9f9f9; border-radius: 5px;">
                    <h4 style="margin-top: 0; color: #d32f2f; line-height: 1.3;">
                        <a href="{article['link']}" style="color: #d32f2f; text-decoration: none;">
                            {article['title']}
                        </a>
                    </h4>
                    <div style="color: #888; margin: 8px 0; font-size: 14px;">
                        <strong>📰 {article['source']}</strong> | {time_indicator} | 
                        <strong>🎯 AI Score: {importance}/10</strong> | 
                        <span style="font-size: 12px;">({ai_source})</span>
                    </div>
                    <div style="margin: 15px 0; line-height: 1.6; color: #333;">
                        {summary_text}
                    </div>
                    <a href="{article['link']}" 
                       style="color: #fff; background: {score_color}; padding: 8px 16px; text-decoration: none; border-radius: 4px; display: inline-block; font-weight: bold;">
                        → Read Full Article
                    </a>
                </div>
                """
        
        html_content += f"""
            <div style="text-align: center; margin-top: 30px; padding: 20px; background: #f0f0f0; border-radius: 5px;">
                <p style="color: #666; font-size: 12px; margin: 0;">
                    🤖 AI-Enhanced China Policy Monitor • 🔄 Updated every 24 hours<br>
                    🌐 Sources: Reuters, BBC, CNN, AP, FT, SCMP, WSJ, Bloomberg, and more<br>
                    <strong>AI Analysis:</strong> {ai_summary}
                </p>
            </div>
        </body>
        </html>
        """
    else:
        subject = f"China Policy News Daily Digest - 0 articles - {current_date}"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #d32f2f;">🇨🇳 China Policy News Daily Digest</h2>
            <p style="color: #666;"><em>No new policy-related articles found today.</em></p>
            <p style="color: #666;">Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </body>
        </html>
        """
    
    # Send email
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = email_user
        msg['To'] = recipient_email
        msg['Subject'] = subject
        
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email_user, email_password)
        server.sendmail(email_user, recipient_email, msg.as_string())
        server.quit()
        
        print(f"✅ Email sent successfully to {recipient_email}")
        print(f"📧 Subject: {subject}")
        
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

def main():
    """Main function"""
    print("🚀 Starting AI-Enhanced China Policy News Monitor...")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load processed articles
    processed_articles = load_processed_articles()
    
    # Fetch all news
    all_articles = fetch_news()
    print(f"\n📰 Total articles fetched: {len(all_articles)}")
    
    if not all_articles:
        print("❌ No articles found from any source")
        send_email([])  # Send empty email
        return
    
    # Filter and analyze with AI
    china_articles = filter_and_analyze_articles(all_articles)
    print(f"\n📊 Found {len(china_articles)} AI-analyzed policy articles from {len(set(a['source'] for a in china_articles))} sources")
    
    # Show top articles by AI score
    print("\n🏆 Top articles by AI importance score:")
    for i, article in enumerate(china_articles[:5], 1):
        score = article.get('importance_score', 0)
        category = article.get('category', 'Other')
        ai_source = article.get('ai_source', 'rule')
        print(f"   {i}. [{score}/10] {category} - {article['title'][:60]}... ({ai_source})")
    
    # Filter out already processed articles
    new_articles = []
    for article in china_articles:
        if article['link'] not in processed_articles:
            new_articles.append(article)
            processed_articles.add(article['link'])
    
    print(f"\n🆕 New articles to send: {len(new_articles)}")
    
    # Send email
    send_email(new_articles)
    
    # Save processed articles
    save_processed_articles(processed_articles)
    
    print("✅ AI-Enhanced China Policy News Monitor completed")

if __name__ == "__main__":
    main()
