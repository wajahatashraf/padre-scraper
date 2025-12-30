import subprocess
import threading
from flask import Flask, jsonify, render_template
from datetime import datetime
import json
from collections import OrderedDict

app = Flask(__name__)

messages = []
scraper_process = None
latest_tweet_ids = OrderedDict()  # Keep track of latest tweet IDs
MAX_TWEETS = 100


def start_scraper():
    global scraper_process, messages, latest_tweet_ids

    messages.clear()
    latest_tweet_ids.clear()

    scraper_process = subprocess.Popen(
        ["python", "scraper.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        bufsize=1
    )

    for line in scraper_process.stdout:
        line = line.strip()

        if line.startswith("[") and line.endswith("]"):
            clean_line = line.strip()
            if clean_line:
                messages.append(clean_line)
                if len(messages) > MAX_TWEETS:
                    messages.pop(0)


@app.route("/")
def home():
    """Render the main page"""
    return render_template("index.html")


@app.route("/start")
def start_scraper_route():
    """Start the scraper"""
    global scraper_process

    if scraper_process is None or scraper_process.poll() is not None:
        threading.Thread(target=start_scraper, daemon=True).start()
        return jsonify({
            "status": "success",
            "message": "✅ Scraper started successfully"
        })
    else:
        return jsonify({
            "status": "info",
            "message": "⚠️ Scraper is already running"
        })


@app.route("/stop")
def stop_scraper_route():
    """Stop the scraper"""
    global scraper_process, messages, latest_tweet_ids
    if scraper_process and scraper_process.poll() is None:
        scraper_process.terminate()
        try:
            scraper_process.wait(timeout=5)
        except:
            scraper_process.kill()
        scraper_process = None

    messages.clear()
    latest_tweet_ids.clear()
    return jsonify({
        "status": "success",
        "message": "✅ Scraper stopped"
    })


@app.route("/status")
def get_status():
    """Get scraper status"""
    global scraper_process

    if scraper_process is None:
        return jsonify({"running": False, "message_count": len(messages), "tweet_count": len(latest_tweet_ids)})
    else:
        return jsonify({
            "running": scraper_process.poll() is None,
            "message_count": len(messages),
            "tweet_count": len(latest_tweet_ids)
        })


@app.route("/messages")
def get_messages():
    """Get processed messages in a nice format"""
    global latest_tweet_ids, messages

    # Process ALL messages, not just the last MAX_TWEETS
    for msg in messages:
        try:
            # Parse the message as JSON
            data = json.loads(msg) if isinstance(msg, str) else msg

            # Check if this is a valid message
            if isinstance(data, list) and len(data) > 2 and data[0] == 5 and data[1] == 13:
                message_data = data[2]
                message_type = message_data.get('type')

                if message_type == 'init':
                    # Initial batch of tweets
                    snapshot = message_data.get('snapshot', {})
                    items = snapshot.get('items', [])

                    for item in items:
                        if 'tweet' in item:
                            tweet_data = process_tweet_data(item)
                            if tweet_data:
                                latest_tweet_ids[tweet_data["original_id"]] = tweet_data

                elif message_type == 'update':
                    # New updates
                    update = message_data.get('update', {})
                    updates = update.get('updates', [])

                    for item in updates:
                        if 'tweet' in item:
                            tweet_data = process_tweet_data(item)
                            if tweet_data:
                                latest_tweet_ids[tweet_data["original_id"]] = tweet_data
                                # Keep only latest 100 tweets
                                if len(latest_tweet_ids) > MAX_TWEETS:
                                    oldest_key = next(iter(latest_tweet_ids))
                                    del latest_tweet_ids[oldest_key]

        except Exception as e:
            print(f"Error processing message: {e}")
            continue

    # Convert to list and sort by timestamp (newest first)
    processed_messages = list(latest_tweet_ids.values())
    processed_messages.sort(key=lambda x: x.get('timestamp', 0), reverse=True)

    return jsonify({
        "count": len(processed_messages),
        "messages": processed_messages
    })


def process_tweet_data(item):
    """Process raw tweet data into a readable format"""
    try:
        tweet = item.get('tweet', {})
        author = tweet.get('author', {})
        profile = author.get('profile', {})
        metrics = tweet.get('metrics', {})

        # Get tweet ID
        tweet_id = tweet.get('id')
        if not tweet_id:
            return None

        # Handle subtweet (if reply or retweet)
        subtweet = tweet.get('subtweet')
        subtweet_content = None
        subtweet_author = None
        if subtweet:
            subtweet_author_data = subtweet.get('author', {})
            subtweet_profile = subtweet_author_data.get('profile', {})
            subtweet_author = {
                "name": subtweet_profile.get('name', 'Unknown'),
                "username": subtweet_author_data.get('handle', 'unknown'),
                "id": subtweet_author_data.get('id')
            }
            subtweet_content = subtweet.get('body', {}).get('text', '')

        # Handle reply to
        reply = tweet.get('reply')
        replying_to = None
        if reply:
            replying_to = {
                "name": f"@{reply.get('handle')}",
                "username": reply.get('handle'),
                "id": None
            }
        elif subtweet_author and tweet.get('type') == 'REPLY':
            # If it's a reply to a subtweet
            replying_to = subtweet_author

        # Format timestamp
        timestamp_ms = tweet.get('created_at', 0)
        if timestamp_ms == 0:
            timestamp_ms = item.get('itemCreatedAt', 0)

        dt = datetime.fromtimestamp(timestamp_ms / 1000)
        formatted = dt.strftime("%I:%M %p · %b %d, %Y")
        if formatted.startswith("0"):
            formatted = formatted[1:]

        # Format relative time
        now = datetime.now()
        diff = now - dt
        if diff.days == 0:
            if diff.seconds < 60:
                relative_time = "Just now"
            elif diff.seconds < 3600:
                relative_time = f"{diff.seconds // 60}m ago"
            else:
                relative_time = f"{diff.seconds // 3600}h ago"
        elif diff.days == 1:
            relative_time = "Yesterday"
        elif diff.days < 7:
            relative_time = f"{diff.days}d ago"
        else:
            relative_time = formatted

        # Extract mentions from body
        body = tweet.get('body', {})
        mentions = []
        for mention in body.get('mentions', []):
            mentions.append(f"@{mention.get('handle')}")

        # Get metrics safely - handle different metric names
        likes = metrics.get('likesCount', metrics.get('likeCount', 0))
        retweets = metrics.get('retweetsCount', metrics.get('retweetCount', 0))
        replies = metrics.get('repliesCount', metrics.get('replyCount', 0))
        bookmarks = metrics.get('bookmarksCount', metrics.get('bookmarkCount', 0))

        # Handle quoted tweet
        quoted = tweet.get('quoted')
        quoted_info = None
        if quoted:
            quoted_info = {
                "id": quoted.get('id'),
                "username": quoted.get('handle'),
                "text": quoted.get('body', {}).get('text', '')
            }

        # Generate X/Twitter URL
        twitter_url = f"https://x.com/{author.get('handle', 'unknown')}/status/{tweet_id}"

        return {
            "id": tweet_id,
            "original_id": tweet_id,
            "twitter_url": twitter_url,
            "type": tweet.get('type', 'TWEET'),
            "timestamp": timestamp_ms,
            "formatted_time": formatted,
            "relative_time": relative_time,
            "author": {
                "name": profile.get('name', 'Unknown'),
                "username": author.get('handle', 'unknown'),
                "avatar": profile.get('avatar', ''),
                "verified": author.get('verified', False),
                "following": author.get('metrics', {}).get('following', 0),
                "followers": author.get('metrics', {}).get('followers', 0)
            },
            "content": {
                "text": body.get('text', ''),
                "mentions": mentions
            },
            "subtweet": {
                "content": subtweet_content,
                "author": subtweet_author
            } if subtweet_content else None,
            "stats": {
                "likes": int(likes),
                "retweets": int(retweets),
                "replies": int(replies),
                "bookmarks": int(bookmarks)
            },
            "replying_to": replying_to,
            "quoted": quoted_info,
            "media": tweet.get('media', {})
        }
    except Exception as e:
        print(f"Error processing tweet: {e}")
        import traceback
        traceback.print_exc()
        return None


@app.route("/clear")
def clear_messages():
    """Clear all messages"""
    global messages, latest_tweet_ids
    messages.clear()
    latest_tweet_ids.clear()
    return jsonify({"status": "success", "message": "Messages cleared"})


if __name__ == "__main__":
    app.run(port=5001, debug=True)