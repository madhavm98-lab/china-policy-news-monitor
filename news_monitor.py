#!/usr/bin/env python3
"""
China Policy News Monitor
Collects policy news related to Chinese government and emails daily digest
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

class ChinaPolicyNewsMonitor:
    def __init__(self):
        # Email configuration
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.email_user = os.getenv('EMAIL_USER')
        self.email_password = os.getenv('EMAIL_PASSWORD')
        self.recipient_email = os.getenv('RECIPIENT_EMAIL')
        
        # News sources configuration
        self.rss_feeds = [
            {
                'name': 'China Daily',
                'url': 'http://www.chinadaily.com.cn/rss/china_rss.xml',
                'category': 'official'
            },
            {
                'name': 'Xinhua News',
                'url': 'http://www.xinhuanet.com/english/rss.xml',
                'category': 'official'
            },
            {
                'name': 'South China Morning Post',
                'url': 'https://www.scmp.com/rss/91/china',
                'category': 'news'
            },
            {
                'name': 'Google News - China Policy',
                'url': 'https://news.google.com/rss/search?q=china+government+policy&hl=en-US&gl=US&ceid=US:en',
                'category': 'aggregated'
            },
            {
                'name': 'Google News - China Economy',
                'url': 'https://news.google.com/rss/search?q=china+economic+policy&hl=en-US&gl=US&ceid=US:en',
                'category': 'aggregated'
            }
        ]
        
        # Policy-related keywords for filtering
        self.policy_keywords = [
            # Economic policy
            'economic policy', 'monetary policy', 'fiscal policy', 'trade policy',
            'belt and road', 'bri', 'made in china 2025', 'dual circulation',
            
            # Government & regulation
            'government policy', 'regulation', 'regulatory', 'ministry', 'ndrc',
            'state council', 'politburo', 'central committee', 'party congress',
            
            # Technology & innovation
            'technology policy', 'innovation policy', 'ai policy', 'data security',
            'cybersecurity law', 'antitrust', 'platform regulation',
            
            # Environment & energy
            'carbon neutral', 'carbon peak', 'environmental policy', 'green policy',
            'renewable energy policy', 'climate policy',
            
            # Social policy
            'social policy', 'education policy', 'healthcare policy', 'housing policy',
            'population policy', 'demographic policy'
        ]
        
        # File to store processed article IDs (to avoid duplicates)
        self.processed_file = 'processed_articles.json'
        
    def load_processed_articles(self) -> Set[str]:
        """Load list of already processed article IDs"""
        try:
            if os.path.exists(self.processed_file):
                with open(self.processed_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('processed', []))
        except Exception as e:
            print(f"Error loading processed articles: {e}")
        return set()
    
    def save_processed_articles(self, processed_ids: Set[str]):
        """Save processed article IDs to file"""
        try:
            # Keep only recent IDs (last 7 days worth)
            current_time = datetime.now()
            week_ago = current_time - timedelta(days=7)
            
            data = {
                'processed': list(processed_ids),
                'last_updated': current_time.isoformat()
            }
            
            with open(self.processed_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving processed articles: {e}")
    
    def generate_article_id(self, title: str, link: str) -> str:
        """Generate unique ID for an article"""
        return hashlib.md5(f"{title}{link}".encode()).hexdigest()
    
    def is_policy_related(self, title: str, description: str) -> tuple[bool, List[str]]:
        """Check if article is policy-related and return matching keywords"""
        text = f"{title} {description}".lower()
        matching_keywords = []
        
        for keyword in self.policy_keywords:
            if keyword.lower() in text:
                matching_keywords.append(keyword)
        
        return len(matching_keywords) > 0, matching_keywords
    
    def fetch_rss_feed(self, feed_config: Dict) -> List[Dict]:
        """Fetch and parse RSS feed"""
        articles = []
        
        try:
            print(f"Fetching from {feed_config['name']}...")
            feed = feedparser.parse(feed_config['url'])
            
            for entry in feed.entries:
                # Extract article information
                title = entry.get('title', 'No title')
                link = entry.get('link', '')
                description = entry.get('description', entry.get('summary', ''))
                published = entry.get('published', '')
                
                # Parse published date
                pub_date = None
                if published:
                    try:
                        pub_date = datetime(*entry.published_parsed[:6])
                    except:
                        pub_date = datetime.now()
                else:
                    pub_date = datetime.now()
                
                # Only include articles from last 48 hours (was 24)
                if pub_date > datetime.now() - timedelta(days=2):
                    articles.append({
                        'title': title,
                        'link': link,
                        'description': description,
                        'published': pub_date,
                        'source': feed_config['name'],
                        'category': feed_config['category']
                    })
            
            print(f"Found {len(articles)} recent articles from {feed_config['name']}")
            
        except Exception as e:
            print(f"Error fetching {feed_config['name']}: {e}")
        
        time.sleep(1)  # Be respectful to servers
        return articles
    
    def collect_news(self) -> List[Dict]:
        """Collect news from all RSS feeds"""
        all_articles = []
        processed_ids = self.load_processed_articles()
        
        for feed_config in self.rss_feeds:
            articles = self.fetch_rss_feed(feed_config)
            
            for article in articles:
                # Generate unique ID
                article_id = self.generate_article_id(article['title'], article['link'])
                
                # Skip if already processed
                if article_id in processed_ids:
                    continue
                
                # Check if policy-related
                is_relevant, keywords = self.is_policy_related(
                    article['title'], 
                    article['description']
                )
                
                if is_relevant:
                    article['id'] = article_id
                    article['keywords'] = keywords
                    all_articles.append(article)
                    processed_ids.add(article_id)
        
        # Save updated processed IDs
        self.save_processed_articles(processed_ids)
        
        return all_articles
    
    def generate_html_email(self, articles: List[Dict]) -> str:
        """Generate HTML email content"""
        if not articles:
            return """
            <html>
            <body>
                <h2>China Policy News Daily Digest</h2>
                <p><em>No new policy-related articles found today.</em></p>
                <p>Generated on: {}</p>
            </body>
            </html>
            """.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # Sort articles by publication date (newest first)
        articles.sort(key=lambda x: x['published'], reverse=True)
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; }}
                .header {{ background-color: #c41e3a; color: white; padding: 20px; text-align: center; }}
                .article {{ border-bottom: 1px solid #eee; padding: 20px 0; }}
                .title {{ font-size: 18px; font-weight: bold; color: #333; margin-bottom: 10px; }}
                .meta {{ color: #666; font-size: 12px; margin-bottom: 10px; }}
                .description {{ margin-bottom: 10px; line-height: 1.5; }}
                .keywords {{ background-color: #f0f0f0; padding: 5px; border-radius: 3px; font-size: 11px; }}
                .source {{ font-weight: bold; }}
                a {{ color: #c41e3a; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🇨🇳 China Policy News Daily Digest</h1>
                <p>Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                <p>Found {len(articles)} policy-related articles</p>
            </div>
        """
        
        for article in articles:
            # Clean description
            description = re.sub(r'<[^>]+>', '', article['description'])[:300]
            if len(description) == 300:
                description += "..."
            
            keywords_str = ", ".join(article['keywords'][:5])  # Show max 5 keywords
            
            html_content += f"""
            <div class="article">
                <div class="title">
                    <a href="{article['link']}" target="_blank">{article['title']}</a>
                </div>
                <div class="meta">
                    <span class="source">{article['source']}</span> | 
                    {article['published'].strftime("%Y-%m-%d %H:%M")} | 
                    Category: {article['category'].title()}
                </div>
                <div class="description">{description}</div>
                <div class="keywords">Keywords: {keywords_str}</div>
            </div>
            """
        
        html_content += """
            <div style="text-align: center; padding: 20px; color: #666; font-size: 12px;">
                <p>This digest was automatically generated by China Policy News Monitor</p>
                <p>To modify your subscription, update your GitHub repository settings</p>
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    def send_email(self, articles: List[Dict]):
        """Send email digest"""
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"China Policy News Digest - {len(articles)} articles - {datetime.now().strftime('%Y-%m-%d')}"
            msg['From'] = self.email_user
            msg['To'] = self.recipient_email
            
            # Generate HTML content
            html_content = self.generate_html_email(articles)
            
            # Create plain text version
            if articles:
                text_content = f"China Policy News Daily Digest - {datetime.now().strftime('%Y-%m-%d')}\n\n"
                for article in articles:
                    text_content += f"Title: {article['title']}\n"
                    text_content += f"Source: {article['source']}\n"
                    text_content += f"Link: {article['link']}\n"
                    text_content += f"Keywords: {', '.join(article['keywords'][:3])}\n\n"
            else:
                text_content = "No new China policy articles found today."
            
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
            
            print(f"✅ Email sent successfully to {self.recipient_email}")
            print(f"📧 Subject: {msg['Subject']}")
            
        except Exception as e:
            print(f"❌ Error sending email: {e}")
    
    def run(self):
        """Main execution function"""
        print("🚀 Starting China Policy News Monitor...")
        print(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Collect news articles
        articles = self.collect_news()
        
        print(f"📰 Found {len(articles)} policy-related articles")
        
        # Send email digest
        if self.email_user and self.email_password and self.recipient_email:
            self.send_email(articles)
        else:
            print("❌ Email credentials not configured")
            print("Set EMAIL_USER, EMAIL_PASSWORD, and RECIPIENT_EMAIL environment variables")
        
        print("✅ China Policy News Monitor completed")

if __name__ == "__main__":
    monitor = ChinaPolicyNewsMonitor()
    monitor.run()
