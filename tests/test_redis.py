import shelve

from redis import Redis

# from twitterhal.conf import settings
from twitterhal.models import RedisList


r = Redis()
db = shelve.open("twitterhal")
tweets = db["posted_tweets"]
tweets = RedisList.wrap(tweets, r, "posted_tweets")
print(tweets)


# lst = RedisList(r, "testlist", settings.RANDOM_POST_TIMES)
lst = RedisList(r, "testlist")
print(lst)
print(len(lst))
item = lst[-1]
del lst[1]
print(lst)
print(len(lst))
lst.append("hej")
print(lst)
lst.insert(1, "nytt värde på pos 1")
print(lst.pop())
print(lst)
lst += lst
print(lst)
lst *= 2
print(lst)
