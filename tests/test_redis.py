from redis import Redis

# from twitterhal.conf import settings
from twitterhal.models import RedisListWrapper

r = Redis()
# lst = RedisListWrapper(r, "testlist", settings.RANDOM_POST_TIMES)
lst = RedisListWrapper(r, "testlist")
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
