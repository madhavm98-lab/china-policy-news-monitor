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
    """Use Groq (free Llama) to analyze and score China/Hong Kong articles"""
    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        print("⚠️ GROQ_API_KEY not set, using rule-based scoring")
        return None
    
    prompt = f"""Analyze this news article about China/Hong Kong policy and provide a JSON response with:
1. relevance_score (0-10): How relevant to China or Hong Kong policy/politics/economy
2. importance_score (0-10): How important/impactful this news is
3. category: One of ["China-Politics", "Hong Kong", "China-Economy", "China-Trade", "China-Technology", "China-Military", "China-Diplomacy", "Other"]
4. key_points: List of 2-3 main points (max 25 words each)
5. summary_one_line: One sentence summary (max 35 words)
6. is_china_hk_related: true/false - Is this specifically about China or Hong Kong?

Title: {title}
Content: {summary[:800]}

Focus ONLY on China and Hong Kong news. Be generous with scoring if it's China/HK related.
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
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 400
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
                    json_match = re.search(r'```json\s*(.*?)\s*```', ai_response, re.DOTALL)
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

def get_rule_based_score(title, summary):
    """Enhanced rule-based scoring for China/Hong Kong focus"""
    text = f"{title} {summary}".lower()
    
    # Primary China/Hong Kong keywords - more inclusive
    china_hk_keywords = [
        # China terms
        'china', 'chinese', 'beijing', 'shanghai', 'guangzhou', 'shenzhen', 'xi jinping', 
        'ccp', 'communist party', 'prc', 'peoples republic', 'mainland china', 'sino-',
        
        # Hong Kong terms  
        'hong kong', 'hongkong', 'hk', 'carrie lam', 'john lee', 'legislative council',
        'legco', 'central government', 'one country two systems',
        
        # Economic centers
        'macau', 'macao', 'pearl river delta', 'greater bay area',
        
        # Taiwan (often relates to China policy)
        'taiwan', 'taipei', 'strait', 'cross-strait'
    ]
    
    # Policy/Economic/Political keywords - be more inclusive
    relevant_keywords = [
        # Politics & Governance
        'policy', 'government', 'political', 'election', 'democracy', 'protest', 'law',
        'regulation', 'legal', 'court', 'parliament', 'congress', 'ministry', 'official',
        'reform', 'crackdown', 'arrest', 'detention', 'security', 'police',
        
        # Economy & Business
        'economy', 'economic', 'trade', 'business', 'market', 'stock', 'investment',
        'gdp', 'growth', 'inflation', 'currency', 'yuan', 'renminbi', 'export', 'import',
        'manufacturing', 'factory', 'company', 'corporate', 'financial', 'bank',
        
        # Technology
        'technology', 'tech', 'digital', 'internet', 'ai', 'artificial intelligence',
        'chip', 'semiconductor', 'huawei', 'tencent', 'alibaba', 'baidu', 'bytedance',
        
        # International Relations
        'diplomacy', 'diplomatic', 'foreign', 'international', 'summit', 'meeting',
        'agreement', 'treaty', 'sanctions', 'tariff', 'trade war', 'us-china', 'biden',
        'america', 'american', 'europe', 'european', 'japan', 'korea', 'asean',
        
        # Regional Issues
        'south china sea', 'belt and road', 'bri', 'military', 'defense', 'weapon',
        'nuclear', 'missile', 'navy', 'army'
    ]
    
    # Check if has China/HK keyword
    has_china_hk = any(keyword in text for keyword in china_hk_keywords)
    
    if not has_china_hk:
        return {
            "relevance_score": 0,
            "importance_score": 0,
            "category": "Other",
            "is_china_hk_related": False,
            "ai_source": "rule_based"
        }
    
    # Count relevant keywords
    relevance_count = sum(1 for keyword in relevant_keywords if keyword in text)
    
    # Base scoring
    base_score = 6  # Higher base for China/HK articles
    relevance_bonus = min(4, relevance_count)  # Up to 4 extra points
    
    final_score = min(10, base_score + relevance_bonus)
    
    # Determine category
    if any(kw in text for kw in ['hong kong', 'hongkong', 'hk', 'carrie lam', 'john lee']):
        category = "Hong Kong"
    elif any(kw in text for kw in ['trade', 'tariff', 'export', 'import', 'trade war']):
        category = "China-Trade"
    elif any(kw in text for kw in ['technology', 'tech', 'ai', 'chip', 'huawei']):
        category = "China-Technology"
    elif any(kw in text for kw in ['military', 'defense', 'weapon', 'navy']):
        category = "China-Military"
    elif any(kw in text for kw in ['economy', 'economic', 'gdp', 'growth']):
        category = "China-Economy"
    elif any(kw in text for kw in ['diplomacy', 'foreign', 'summit', 'meeting']):
        category = "China-Diplomacy"
    elif any(kw in text for kw in ['government', 'political', 'xi jinping', 'ccp']):
        category = "China-Politics"
    else:
        category = "Other"
    
    return {
        "relevance_score": final_score,
        "importance_score": final_score,
        "category": category,
        "is_china_hk_related": True,
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

def clean_article_summary(summary):
    """Clean article summary from HTML/JS content"""
    if not summary:
        return "No summary available"
    
    # Remove HTML tags
    summary = re.sub(r'<[^>]+>', ' ', summary)
    
    # Remove common JavaScript/tracking code patterns
    js_patterns = [
        r'function\s*\([^)]*\)\s*\{[^}]*\}',
        r'var\s+\w+\s*=\s*[^;]+;',
        r'window\.\w+\s*=\s*[^;]+;',
        r'NREUM\.[^;]+;',
        r'loader_config\s*=\s*\{[^}]+\}',
        r'gadSlots\s*=\s*\{[^}]*\}',
        r'@import\s+url\([^)]+\)',
        r'!function\([^)]*\)\{[^}]*\}',
        r'\w+\.\w+\s*=\s*\{[^}]*\}',
        r'licenseKey[^;]+;',
        r'applicationID[^;]+;',
    ]
    
    for pattern in js_patterns:
        summary = re.sub(pattern, '', summary, flags=re.IGNORECASE)
    
    # Remove excessive whitespace and special characters
    summary = re.sub(r'\s+', ' ', summary)
    summary = re.sub(r'[^\w\s\.,!?;:\-\'"()%$]', ' ', summary)
    
    # Remove common tracking/ad text
    remove_phrases = [
        'South China Morning Post',
        'The Straits Times',
        'window.',
        'function(',
        'var ',
        'REUTERS',
        'loader_config',
        'gadSlots',
        'NREUM',
        'trustKey',
        'accountID'
    ]
    
    for phrase in remove_phrases:
        summary = summary.replace(phrase, '')
    
    # Clean up and truncate
    summary = summary.strip()
    sentences = summary.split('. ')
    
    # Take first few meaningful sentences
    clean_sentences = []
    for sentence in sentences:
        if len(sentence) > 30 and not any(skip in sentence.lower() for skip in 
            ['cookie', 'subscribe', 'newsletter', 'javascript', 'advertisement']):
            clean_sentences.append(sentence)
        if len(clean_sentences) >= 3:  # Max 3 sentences
            break
    
    result = '. '.join(clean_sentences)
    if result:
        return result[:800]  # Max 800 chars
    else:
        return summary[:300]  # Fallback to original (truncated)

def fetch_china_hk_news():
    """Fetch news specifically focused on China and Hong Kong"""
    feeds = [
        # China-focused sources
        ('South China Morning Post - China', 'https://www.scmp.com/rss/2/feed'),
        ('South China Morning Post - Hong Kong', 'https://www.scmp.com/rss/3/feed'),
        ('China Daily', 'https://www.chinadaily.com.cn/rss/china_rss.xml'),
        ('Xinhua China', 'http://www.xinhuanet.com/english/rss/china.xml'),
        
        # Major international sources with China coverage
        ('Reuters Asia', 'https://feeds.reuters.com/reuters/asiaNews'),
        ('Reuters China', 'https://feeds.reuters.com/reuters/chinNews'),
        ('BBC Asia-Pacific', 'https://feeds.bbci.co.uk/news/world/asia/rss.xml'),
        ('CNN Asia', 'https://rss.cnn.com/rss/cnn_asia.rss'),
        
        # Business sources with China focus
        ('Bloomberg Asia', 'https://feeds.bloomberg.com/politics/news.rss'),
        ('Wall Street Journal Asia', 'https://feeds.a.dj.com/rss/RSSAsiaNews.xml'),
        
        # Regional Asia sources
        ('Japan Times Asia', 'https://www.japantimes.co.jp/feed/asia-pacific/'),
        ('Straits Times Asia', 'https://www.straitstimes.com/news/asia/rss.xml'),
        ('Nikkei Asia', 'https://asia.nikkei.com/rss/feed/nar'),
        
        # Specialized sources
        ('Foreign Policy China', 'https://foreignpolicy.com/feed/'),
        ('Asia Times', 'http://www.atimes.com/feed/'),
    ]
    
    all_articles = []
    cutoff_date = datetime.now() - timedelta(hours=24)
    
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
            
            for entry in feed.entries:
                # Parse publication date
                pub_date = None
                
                for date_field in ['published_parsed', 'updated_parsed', 'created_parsed']:
                    if hasattr(entry, date_field) and getattr(entry, date_field):
                        try:
                            pub_date = datetime(*getattr(entry, date_field)[:6])
                            break
                        except:
                            continue
                
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
                    
                    # Get and clean article summary
                    raw_summary = entry.get('summary', entry.get('description', ''))
                    clean_summary = clean_article_summary(raw_summary)
                    
                    article = {
                        'title': entry.get('title', ''),
                        'link': entry.get('link', ''),
                        'summary': clean_summary,
                        'published': pub_date.strftime('%Y-%m-%d %H:%M UTC'),
                        'source': source_name,
                        'hours_ago': int((datetime.now() - pub_date).total_seconds() / 3600)
                    }
                    all_articles.append(article)
            
            print(f"Found {recent_count} recent articles from {source_name}")
            
        except Exception as e:
            print(f"Error fetching {source_name}: {e}")
    
    return all_articles

def is_china_hk_related(title, summary):
    """More inclusive function to check if article is China/Hong Kong related"""
    text = f"{title} {summary}".lower()
    
    # Be very inclusive for China/Hong Kong keywords
    keywords = [
        # Core China/HK terms
        'china', 'chinese', 'beijing', 'shanghai', 'hong kong', 'hongkong', 'hk',
        'xi jinping', 'ccp', 'communist party', 'prc', 'mainland china',
        
        # Taiwan (China-related)
        'taiwan', 'taipei', 'strait', 'cross-strait',
        
        # Economic regions
        'macau', 'macao', 'shenzhen', 'guangzhou', 'pearl river delta',
        
        # Chinese companies/brands
        'huawei', 'tencent', 'alibaba', 'baidu', 'bytedance', 'tiktok', 'wechat',
        'byd', 'xiaomi', 'lenovo', 'didi',
        
        # China-US relations
        'sino-', 'us-china', 'china-us', 'biden china', 'trump china',
        
        # Regional terms that often involve China
        'south china sea', 'east china sea', 'belt and road', 'bri', 'asean china'
    ]
    
    return any(keyword in text for keyword in keywords)

def filter_and_analyze_articles(articles):
    """Filter and analyze China/Hong Kong articles with AI"""
    print(f"\n🔍 Filtering {len(articles)} articles for China/Hong Kong relevance...")
    
    china_hk_articles = []
    
    for article in articles:
        if is_china_hk_related(article['title'], article['summary']):
            print(f"✓ China/HK related: {article['title'][:60]}...")
            
            # Get AI analysis
            ai_analysis = analyze_article_with_groq(article['title'], article['summary'])
            
            if ai_analysis:
                article.update(ai_analysis)
                # Only include if AI confirms it's China/HK related
                if ai_analysis.get('is_china_hk_related', True):
                    china_hk_articles.append(article)
                    print(f"   🤖 AI Score: {ai_analysis.get('importance_score', 0)}/10 | "
                          f"Category: {ai_analysis.get('category', 'Unknown')}")
                else:
                    print(f"   ❌ AI filtered out as not China/HK related")
            else:
                # Use rule-based analysis
                rule_analysis = get_rule_based_score(article['title'], article['summary'])
                if rule_analysis.get('is_china_hk_related', False):
                    article.update(rule_analysis)
                    china_hk_articles.append(article)
                    print(f"   📏 Rule Score: {rule_analysis.get('importance_score', 0)}/10")
    
    # Sort by importance score
    china_hk_articles.sort(key=lambda x: x.get('importance_score', 0), reverse=True)
    
    return china_hk_articles

def send_email(articles):
    """Send email with China/Hong Kong articles"""
    email_user = os.environ.get('EMAIL_USER')
    email_password = os.environ.get('EMAIL_PASSWORD')
    recipient_email = os.environ.get('RECIPIENT_EMAIL')
    
    if not all([email_user, email_password, recipient_email]):
        print("❌ Email credentials not configured")
        return
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    if articles:
        subject = f"🇨🇳🇭🇰 China & Hong Kong Policy News - {len(articles)} articles - {current_date}"
        
        # Group articles by category
        categories = {}
        for article in articles:
            cat = article.get('category', 'Other')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(article)
        
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto;">
            <h2 style="color: #d32f2f; text-align: center; border-bottom: 2px solid #d32f2f; padding-bottom: 10px;">
                🇨🇳🇭🇰 China & Hong Kong Policy News
            </h2>
            <div style="text-align: center; color: #666; margin-bottom: 20px;">
                <p><strong>📅 Date:</strong> {current_date} | <strong>📊 Articles:</strong> {len(articles)}</p>
                <p style="font-size: 14px; color: #888;">
                    🎯 China & Hong Kong Focus • ⏰ Last 24 hours • 🤖 AI-Enhanced
                </p>
            </div>
            <hr style="border: 1px solid #ddd; margin: 20px 0;">
        """
        
        # Sort categories by highest importance article in each
        for category, cat_articles in sorted(categories.items(), 
                                           key=lambda x: max(a.get('importance_score', 0) for a in x[1]), 
                                           reverse=True):
            
            category_icon = {
                'Hong Kong': '🇭🇰',
                'China-Politics': '🏛️',
                'China-Economy': '💰',
                'China-Trade': '🚢',
                'China-Technology': '💻',
                'China-Military': '⚔️',
                'China-Diplomacy': '🤝'
            }.get(category, '📰')
            
            html_content += f"""
            <h3 style="color: #d32f2f; border-bottom: 1px solid #ddd; padding-bottom: 5px; margin-top: 25px;">
                {category_icon} {category} ({len(cat_articles)} articles)
            </h3>
            """
            
            for article in cat_articles:
                hours_ago = article.get('hours_ago', 0)
                time_indicator = f"🕐 {hours_ago}h ago" if hours_ago < 24 else f"📅 {article['published']}"
                
                importance = article.get('importance_score', 0)
                ai_source = article.get('ai_source', 'unknown')
                
                # Color coding based on importance
                if importance >= 8:
                    score_color = "#d32f2f"  # Red - high importance
                    border_color = "#d32f2f"
                elif importance >= 6:
                    score_color = "#ff8800"  # Orange - medium importance
                    border_color = "#ff8800"
                else:
                    score_color = "#666"     # Gray - lower importance
                    border_color = "#ccc"
                
                html_content += f"""
                <div style="margin-bottom: 25px; padding: 20px; border-left: 4px solid {border_color}; background: #f9f9f9; border-radius: 5px;">
                    <h4 style="margin-top: 0; color: #d32f2f; line-height: 1.3;">
                        <a href="{article['link']}" style="color: #d32f2f; text-decoration: none;">
                            {article['title']}
                        </a>
                    </h4>
                    <div style="color: #888; margin: 8px 0; font-size: 14px;">
                        <strong>📰 {article['source']}</strong> | {time_indicator} | 
                        <strong style="color: {score_color};">🎯 Score: {importance}/10</strong> | 
                        <span style="font-size: 12px;">({ai_source})</span>
                    </div>
                    <div style="margin: 15px 0; line-height: 1.6; color: #333;">
                        {article['summary']}
                    </div>
                    <a href="{article['link']}" 
                       style="color: #fff; background: {score_color}; padding: 10px 18px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold; margin-top: 10px;">
                        → Read Full Article
                    </a>
                </div>
                """
        
        html_content += f"""
            <div style="text-align: center; margin-top: 30px; padding: 20px; background: #f0f0f0; border-radius: 5px;">
                <p style="color: #666; font-size: 12px; margin: 0;">
                    🤖 AI-Enhanced China & Hong Kong News Monitor<br>
                    🔄 Updated daily at 8:00 AM UTC • 🎯 Focused on China & Hong Kong only<br>
                    📊 Sources: SCMP, China Daily, Reuters, BBC, Bloomberg, and more
                </p>
            </div>
        </body>
        </html>
        """
    else:
        subject = f"China & Hong Kong Policy News - No articles found - {current_date}"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #d32f2f;">🇨🇳🇭🇰 China & Hong Kong Policy News</h2>
            <p style="color: #666;"><em>No new China or Hong Kong policy articles found today.</em></p>
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
    print("🚀 Starting China & Hong Kong Focused News Monitor...")
    print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load processed articles
    processed_articles = load_processed_articles()
    
    # Fetch China/Hong Kong focused news
    all_articles = fetch_china_hk_news()
    print(f"\n📰 Total articles fetched: {len(all_articles)}")
    
    if not all_articles:
        print("❌ No articles found from any source")
        send_email([])
        return
    
    # Filter and analyze with AI
    china_hk_articles = filter_and_analyze_articles(all_articles)
    print(f"\n📊 Found {len(china_hk_articles)} China/Hong Kong articles")
    
    # Show top articles by score
    if china_hk_articles:
        print("\n🏆 Top China/Hong Kong articles by importance:")
        for i, article in enumerate(china_hk_articles[:5], 1):
            score = article.get('importance_score', 0)
            category = article.get('category', 'Other')
            print(f"   {i}. [{score}/10] {category} - {article['title'][:60]}...")
    
    # Filter out already processed articles
    new_articles = []
    for article in china_hk_articles:
        if article['link'] not in processed_articles:
            new_articles.append(article)
            processed_articles.add(article['link'])
    
    print(f"\n🆕 New articles to send: {len(new_articles)}")
    
    # Send email
    send_email(new_articles)
    
    # Save processed articles
    save_processed_articles(processed_articles)
    
    print("✅ China & Hong Kong News Monitor completed")

if __name__ == "__main__":
    main()
