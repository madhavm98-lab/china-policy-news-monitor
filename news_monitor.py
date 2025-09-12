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

def fetch_news():
    """Fetch news from multiple RSS feeds"""
    feeds = [
        # Major international news sources
        ('Reuters World', 'https://feeds.reuters.com/reuters/worldNews'),
        ('BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml'),
        ('CNN World', 'https://rss.cnn.com/rss/edition.rss'),
        ('AP News', 'https://feeds.apnews.com/apnews/World'),
        ('Financial Times', 'https://www.ft.com/world?format=rss'),
        
        # China-focused sources
        ('South China Morning Post', 'https://www.scmp.com/rss/91/feed'),
        ('China Daily', 'https://www.chinadaily.com.cn/rss/world_rss.xml'),
        ('Xinhua World', 'http://www.xinhuanet.com/english/rss/world.xml'),
        
        # Economic/Business sources
        ('Bloomberg Asia', 'https://feeds.bloomberg.com/markets/news.rss'),
        ('WSJ World', 'https://feeds.a.dj.com/rss/RSSWorldNews.xml'),
    ]
    
    all_articles = []
    cutoff_date = datetime.now() - timedelta(days=1)  # Only articles from last 24 hours
    
    for source_name, feed_url in feeds:
        try:
            print(f"Fetching from {source_name}...")
            
            # Add headers to avoid blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(feed_url, headers=headers, timeout=10)
            feed = feedparser.parse(response.content)
            
            recent_count = 0
            for entry in feed.entries:
                # Parse publication date
                pub_date = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    pub_date = datetime(*entry.updated_parsed[:6])
                
                # Only include recent articles
                if pub_date and pub_date >= cutoff_date:
                    recent_count += 1
                    article = {
                        'title': entry.get('title', ''),
                        'link': entry.get('link', ''),
                        'summary': entry.get('summary', entry.get('description', '')),
                        'published': pub_date.strftime('%Y-%m-%d %H:%M'),
                        'source': source_name
                    }
                    all_articles.append(article)
            
            print(f"Found {recent_count} recent articles from {source_name}")
            
        except Exception as e:
            print(f"Error fetching {source_name}: {e}")
    
    return all_articles

def is_china_policy_related(title, summary):
    """Enhanced function to check if article is China policy-related"""
    text = f"{title} {summary}".lower()
    
    # Primary China keywords - must have at least one
    china_keywords = [
        'china', 'beijing', 'shanghai', 'guangzhou', 'shenzhen',
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

def filter_china_policy_articles(articles):
    """Filter articles related to China policy with enhanced criteria"""
    filtered_articles = []
    
    print("\n🔍 Analyzing articles for China policy relevance...")
    for article in articles:
        if is_china_policy_related(article['title'], article['summary']):
            filtered_articles.append(article)
            print(f"✓ MATCH: {article['title'][:80]}...")
        else:
            print(f"✗ Skip: {article['title'][:80]}...")
    
    return filtered_articles

def send_email(articles):
    """Send email with the articles"""
    email_user = os.environ.get('EMAIL_USER')
    email_password = os.environ.get('EMAIL_PASSWORD')
    recipient_email = os.environ.get('RECIPIENT_EMAIL')
    
    if not all([email_user, email_password, recipient_email]):
        print("❌ Email credentials not configured")
        return
    
    # Create email content
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    if articles:
        subject = f"China Policy News Digest - {len(articles)} articles - {current_date}"
        
        # HTML email body
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2 style="color: #d32f2f;">🇨🇳 China Policy News Daily Digest</h2>
            <p style="color: #666;"><strong>Date:</strong> {current_date}</p>
            <p style="color: #666;"><strong>Articles Found:</strong> {len(articles)}</p>
            <hr style="border: 1px solid #ddd;">
        """
        
        for i, article in enumerate(articles, 1):
            html_content += f"""
            <div style="margin-bottom: 25px; padding: 15px; border-left: 4px solid #d32f2f; background: #f9f9f9;">
                <h3 style="margin-top: 0; color: #d32f2f;">
                    <a href="{article['link']}" style="color: #d32f2f; text-decoration: none;">{i}. {article['title']}</a>
                </h3>
                <p style="color: #666; margin: 5px 0;"><strong>Source:</strong> {article['source']} | <strong>Published:</strong> {article['published']}</p>
                <p style="margin: 10px 0;">{article['summary'][:400]}{'...' if len(article['summary']) > 400 else ''}</p>
                <a href="{article['link']}" style="color: #d32f2f; text-decoration: none;">→ Read Full Article</a>
            </div>
            """
        
        html_content += """
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
    print("🚀 Starting China Policy News Monitor...")
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
    
    # Filter for China policy articles
    china_articles = filter_china_policy_articles(all_articles)
    print(f"📰 Found {len(china_articles)} policy-related articles")
    
    # Filter out already processed articles
    new_articles = []
    for article in china_articles:
        if article['link'] not in processed_articles:
            new_articles.append(article)
            processed_articles.add(article['link'])
    
    print(f"🆕 New articles to send: {len(new_articles)}")
    
    # Send email
    send_email(new_articles)
    
    # Save processed articles
    save_processed_articles(processed_articles)
    
    print("✅ China Policy News Monitor completed")

if __name__ == "__main__":
    main()
