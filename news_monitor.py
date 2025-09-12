#!/usr/bin/env python3
"""
DEBUG VERSION - China Policy News Monitor
This version includes extensive debugging to identify issues
"""

import feedparser
import requests
import smtplib
import json
import re
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Set
import os
import hashlib
import time

class ChinaPolicyNewsMonitorDebug:
    def __init__(self):
        # Email configuration
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email_user = os.getenv('EMAIL_USER')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.recipient_email = os.getenv('RECIPIENT_EMAIL')
        
        # Simple, reliable RSS feeds for testing
        self.rss_feeds = [
            {
                'name': 'BBC World',
                'url': 'http://feeds.bbci.co.uk/news/world/rss.xml',
                'category': 'test'
            },
            {
                'name': 'Reuters Top News',
                'url': 'https://feeds.reuters.com/reuters/topNews',
                'category': 'test'
            },
            {
                'name': 'Google News - China',
                'url': 'https://news.google.com/rss/search?q=china&hl=en-US&gl=US&ceid=US:en',
                'category': 'test'
            },
            {
                'name': 'CNN RSS',
                'url': 'http://rss.cnn.com/rss/edition.rss',
                'category': 'test'
            }
        ]
        
        # Very broad keywords for testing
        self.policy_keywords = [
            'china', 'chinese', 'beijing', 'government', 'policy', 'economic', 
            'trade', 'president', 'minister', 'official', 'state', 'national',
            'xi jinping', 'communist', 'party', 'congress', 'council'
        ]
        
        # File to store processed article IDs
        self.processed_file = 'processed_articles.json'
        
    def load_processed_articles(self) -> Set[str]:
        """Load list of already processed article IDs"""
        try:
            if os.path.exists(self.processed_file):
                with open(self.processed_file, 'r') as f:
                    data = json.load(f)
                    processed_set = set(data.get('processed', []))
                    print(f"🔍 DEBUG: Loaded {len(processed_set)} processed articles from file")
                    return processed_set
            else:
                print("🔍 DEBUG: No processed articles file found - starting fresh")
        except Exception as e:
            print(f"🔍 DEBUG: Error loading processed articles: {e}")
        return set()
    
    def save_processed_articles(self, processed_ids: Set[str]):
        """Save processed article IDs to file"""
        try:
            data = {
                'processed': list(processed_ids),
                'last_updated': datetime.now().isoformat()
            }
            
            with open(self.processed_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"🔍 DEBUG: Saved {len(processed_ids)} processed article IDs")
        except Exception as e:
            print(f"🔍 DEBUG: Error saving processed articles: {e}")
    
    def generate_article_id(self, title: str, link: str) -> str:
        """Generate unique ID for an article"""
        return hashlib.md5(f"{title}{link}".encode()).hexdigest()[:12]
    
    def is_policy_related(self, title: str, description: str) -> tuple[bool, List[str]]:
    """Accept ALL articles for testing"""
    return True, ["test"]  # Accept everything!
    
    def fetch_rss_feed(self, feed_config: Dict) -> List[Dict]:
        """Fetch and parse RSS feed with extensive debugging"""
        articles = []
        
        try:
            print(f"\n🌐 DEBUG: Fetching from {feed_config['name']}...")
            print(f"   URL: {feed_config['url']}")
            
            # Try to fetch the feed
            feed = feedparser.parse(feed_config['url'])
            
            # Check for feed parsing errors
            if hasattr(feed, 'bozo') and feed.bozo:
                print(f"   ⚠️ Feed parsing warning: {feed.bozo_exception}")
            
            print(f"   Feed status: {getattr(feed, 'status', 'Unknown')}")
            print(f"   Feed title: {getattr(feed.feed, 'title', 'No title')}")
            print(f"   Total entries found: {len(feed.entries)}")
            
            if len(feed.entries) == 0:
                print(f"   ❌ No entries found in feed!")
                return articles
            
            # Process each entry
            for i, entry in enumerate(feed.entries[:5]):  # Only process first 5 for debugging
                print(f"\n   📰 Processing entry {i+1}:")
                
                # Extract article information
                title = entry.get('title', 'No title')
                link = entry.get('link', '')
                description = entry.get('description', entry.get('summary', ''))
                published = entry.get('published', '')
                
                print(f"      Title: {title}")
                print(f"      Link: {link[:60]}...")
                print(f"      Published: {published}")
                
                # Parse published date
                pub_date = None
                if published:
                    try:
                        pub_date = datetime(*entry.published_parsed[:6])
                        print(f"      Parsed date: {pub_date}")
                    except Exception as date_error:
                        print(f"      Date parsing error: {date_error}")
                        pub_date = datetime.now()
                else:
                    pub_date = datetime.now()
                    print(f"      No published date, using current time")
                
                # Check if article is recent (last 7 days for debugging)
                days_old = (datetime.now() - pub_date).days
                print(f"      Days old: {days_old}")
                
                if pub_date > datetime.now() - timedelta(days=7):  # 7 days for debugging
                    articles.append({
                        'title': title,
                        'link': link,
                        'description': description,
                        'published': pub_date,
                        'source': feed_config['name'],
                        'category': feed_config['category']
                    })
                    print(f"      ✅ Added to articles list")
                else:
                    print(f"      ❌ Too old, skipping")
            
            print(f"   📊 Final count: {len(articles)} recent articles from {feed_config['name']}")
            
        except Exception as e:
            print(f"   ❌ Error fetching {feed_config['name']}: {e}")
            print(f"   Error type: {type(e).__name__}")
        
        time.sleep(2)  # Be extra respectful to servers
        return articles
    
    def collect_news(self) -> List[Dict]:
        """Collect news from all RSS feeds with debugging"""
        print("🚀 DEBUG: Starting news collection...")
        all_articles = []
        processed_ids = self.load_processed_articles()
        
        for feed_config in self.rss_feeds:
            articles = self.fetch_rss_feed(feed_config)
            
            print(f"\n🔍 DEBUG: Processing {len(articles)} articles from {feed_config['name']}")
            
            for article in articles:
                # Generate unique ID
                article_id = self.generate_article_id(article['title'], article['link'])
                print(f"   Article ID: {article_id}")
                
                # Skip if already processed
                if article_id in processed_ids:
                    print(f"   ⏭️ Skipping - already processed")
                    continue
                
                # Check if policy-related (with debugging output)
                is_relevant, keywords = self.is_policy_related(
                    article['title'], 
                    article['description']
                )
                
                if is_relevant:
                    article['id'] = article_id
                    article['keywords'] = keywords
                    all_articles.append(article)
                    processed_ids.add(article_id)
                    print(f"   ✅ ADDED: Relevant article found!")
                else:
                    print(f"   ❌ SKIPPED: Not relevant")
        
        # Save updated processed IDs
        self.save_processed_articles(processed_ids)
        
        print(f"\n📊 DEBUG: Final results:")
        print(f"   Total relevant articles found: {len(all_articles)}")
        print(f"   Total processed IDs: {len(processed_ids)}")
        
        return all_articles
    
    def generate_debug_email(self, articles: List[Dict]) -> str:
        """Generate debug email with detailed information"""
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; }}
                .header {{ background-color: #c41e3a; color: white; padding: 20px; text-align: center; }}
                .debug {{ background-color: #f0f8ff; padding: 15px; margin: 10px 0; border-left: 4px solid #007acc; }}
                .article {{ border-bottom: 1px solid #eee; padding: 20px 0; }}
                .title {{ font-size: 18px; font-weight: bold; color: #333; margin-bottom: 10px; }}
                .meta {{ color: #666; font-size: 12px; margin-bottom: 10px; }}
                .keywords {{ background-color: #f0f0f0; padding: 5px; border-radius: 3px; font-size: 11px; }}
                a {{ color: #c41e3a; text-decoration: none; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🔍 DEBUG: China Policy News Monitor</h1>
                <p>Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                <p>Found {len(articles)} articles</p>
            </div>
            
            <div class="debug">
                <h3>🔧 Debug Information:</h3>
                <p><strong>Feed Sources Tested:</strong> BBC, Reuters, Google News, CNN</p>
                <p><strong>Keywords Used:</strong> Very broad (china, government, policy, etc.)</p>
                <p><strong>Time Window:</strong> Last 7 days</p>
                <p><strong>System Status:</strong> {"✅ Working" if len(articles) > 0 else "❌ Issue detected"}</p>
            </div>
        """
        
        if len(articles) == 0:
            html_content += """
            <div class="debug">
                <h3>❌ No Articles Found - Possible Issues:</h3>
                <ul>
                    <li>RSS feeds might be blocked or down</li>
                    <li>Network connectivity issues</li>
                    <li>All articles already processed</li>
                    <li>Filtering too strict</li>
                </ul>
                <p><strong>Next Steps:</strong> Check GitHub Actions logs for detailed error messages</p>
            </div>
            """
        else:
            html_content += f"""
            <div class="debug">
                <h3>✅ Success! Found {len(articles)} articles</h3>
                <p>The system is working correctly. Your regular monitor should find articles too.</p>
            </div>
            """
        
        # Add articles
        for article in articles:
            description = re.sub(r'<[^>]+>', '', article['description'])[:200]
            keywords_str = ", ".join(article['keywords'][:5])
            
            html_content += f"""
            <div class="article">
                <div class="title">
                    <a href="{article['link']}" target="_blank">{article['title']}</a>
                </div>
                <div class="meta">
                    {article['source']} | {article['published'].strftime("%Y-%m-%d %H:%M")}
                </div>
                <div>{description}</div>
                <div class="keywords">Keywords: {keywords_str}</div>
            </div>
            """
        
        html_content += """
        </body>
        </html>
        """
        
        return html_content
    
    def send_email(self, articles: List[Dict]):
        """Send debug email"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"DEBUG: China News Monitor - {len(articles)} articles found"
            msg['From'] = self.email_user
            msg['To'] = self.recipient_email
            
            # Generate HTML content
            html_content = self.generate_debug_email(articles)
            
            # Create plain text version
            text_content = f"DEBUG: China News Monitor Results\n\n"
            text_content += f"Found {len(articles)} articles\n"
            text_content += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            
            if len(articles) == 0:
                text_content += "No articles found. Check GitHub Actions logs for details.\n"
            else:
                text_content += "Articles found:\n\n"
                for article in articles:
                    text_content += f"- {article['title']}\n"
                    text_content += f"  Source: {article['source']}\n"
                    text_content += f"  Keywords: {', '.join(article['keywords'][:3])}\n\n"
            
            # Attach parts
            part1 = MIMEText(text_content, 'plain')
            part2 = MIMEText(html_content, 'html')
            
            msg.attach(part1)
            msg.attach(part2)
            
            # Send email
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.email_user, self.email_password)
            server.send_message(msg)
            server.quit()
            
            print(f"✅ DEBUG email sent successfully to {self.recipient_email}")
            
        except Exception as e:
            print(f"❌ Error sending debug email: {e}")
    
    def run(self):
        """Main execution function with debugging"""
        print("🔍 Starting DEBUG version of China Policy News Monitor...")
        print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📧 Email user: {self.email_user}")
        print(f"📧 Recipient: {self.recipient_email}")
        
        # Collect news articles
        articles = self.collect_news()
        
        print(f"\n📊 FINAL RESULTS:")
        print(f"   Found {len(articles)} relevant articles")
        
        # Send debug email
        if self.email_user and self.email_password and self.recipient_email:
            self.send_email(articles)
        else:
            print("❌ Email credentials not configured")
        
        print("✅ DEBUG run completed")

if __name__ == "__main__":
    monitor = ChinaPolicyNewsMonitorDebug()
    monitor.run()
