import twitter


class TwitterApi(twitter.Api):
    """
    The sole reason for this is to make sure `tweet_mode` is sent with POST
    requests, not just GET. Hopefully my pull request gets accepted and this
    can be trashed. https://github.com/bear/python-twitter/pull/660
    """
    def _RequestUrl(self, url, verb, data=None, json=None, enforce_auth=True):
        if not data:
            data = {}
        data["tweet_mode"] = self.tweet_mode
        return super()._RequestUrl(url, verb, data, json, enforce_auth)
