# Import statements
import argparse
import urllib
import requests
from bs4 import BeautifulSoup
from urllib.request import urlopen
from dateutil.parser import parse
from dateutil import parser
from collections import defaultdict
import re
import pickle
import os
import pandas as pd
import numpy as np
import glob
import datetime

config = json.load(open('../config.json', 'r'))
MC_API_KEY = config['MC_API_KEY']
SERP_API_KEY = config['SERP_API_KEY']

# Set up MediaCloud API
import mediacloud.api
with open('MC_API_KEY.txt','r') as f:
    MC_API_KEY = f.read()
mc = mediacloud.api.MediaCloud(MC_API_KEY)
mc_metadata = ['ap_syndicated','language','media_id','media_name','publish_date','title','guid','url','word_count']
mc_ids = pd.read_pickle('mediacloud_ids.pkl')
mc_ids.reset_index(drop=True, inplace=True)

# Set up SerpAPI
from serpapi.google_search_results import GoogleSearchResults
if SERP_API_KEY == "":
    with open('SERP_API_KEY.txt','r') as f:
        SERP_API_KEY = f.read()
query_params = {"location":"United States", "device":"desktop", "hl":"en", "gl":"us", "serp_api_key":SERP_API_KEY}
CC_KEYWORDS = ['climate_change','global_warming','fossil_fuels','carbon_dioxide','co2']
client = GoogleSearchResults(query_params)

def do_serpapi(domain,keyword):
    """
    Wrapper script for running a SerpAPI query.
    :param domain: str website name, beginning with "www", e.g. "www.foxnews.com".
    :param keyword: str keyword for doing Google search.
    :return: list of dictionaries
    """
    keyword = keyword.replace('_',' ').replace('+',' ').replace('-',' ')
    client.params_dict["q"] = "site:{} {}".format(domain,keyword) # Update query to restrict to particular site
    print('Searching w/ query: {}...'.format(client.params_dict["q"]))
    page_no = 1
    client.params_dict["start"] = (page_no-1)*10                  # Update pagination

    dict_list = []
    while 'error' not in client.get_dict(): # Get results as long as more pages exist
        dict_list.append(client.get_dict())
        page_no += 1
        client.params_dict["start"] = (page_no-1)*10

    return dict_list

def parse_serpapi_results(d_list):
    """
    Script for parsing results returned from do_serpapi().
    :param d_list: List of dictionaries returned by do_serpapi().
    :return: list of URLs with meta information (title, publish date)
    """
    meta = []
    for d in d_list:
        if 'error' in d:
            print(d['error'])
        elif d['search_metadata']['status'] == 'Success':
            res = d['organic_results']
            page_no = d['search_information']['page_number'] if 'page_number' in d['search_information'] else 1
            print('Number of results on page {}: {}'.format(page_no,len(res)))
            meta.extend([(x['title'],x['link'],x['date']) if 'date' in x
                        else (x['title'],x['link']) for x in res])
        else:
            print("API get failure")
    return meta


def get_mc_urls():
    """
    Generates `mediacloud_df.pkl`, a dataframe w/ output from MediaCloud.
    """
    # Collect stories from each outlet using MediaCloud
    if not os.path.exists('./mediacloud'):
        os.mkdir('./mediacloud')
    for curr_outlet_ix in mc_ids.index:
        curr_outlet_id = mc_ids.iloc[curr_outlet_ix]['media_id']
        curr_outlet_stance = mc_ids.iloc[curr_outlet_ix]['leaning']
        fetch_size = 5000
        stories = []
        last_processed_stories_id = 0
        for start_year in range(2020,2021,5): # Start collecting stories from Jan. 1, 2000
            while len(stories) < 10000:
                fetched_stories = mc.storyList('(climate AND chang*) OR (global AND warming) OR (carbon AND dioxide) OR (co2) OR (fossil AND fuel*) AND media_id:{}'.format(curr_outlet_id),
                                               solr_filter=mc.publish_date_query(datetime.date(start_year,1,1), datetime.date(start_year+4,12,31)),
                                               last_processed_stories_id=last_processed_stories_id, rows= fetch_size)
                stories.extend(fetched_stories)
                if len( fetched_stories) < fetch_size:
                    break
                last_processed_stories_id = stories[-1]['processed_stories_id']
        if len(stories) > 0:
            df = pd.DataFrame({key: [s[key] for s in stories] for key in mc_metadata})
            df['topic'] = ['cc']*len(df)
            df['stance'] = curr_outlet_stance
            df.sort_values(by='publish_date')

            OUTLET_NAME = df['media_name'].iloc[0].lower().replace(' ','_')
            df.to_pickle(os.path.join('mediacloud','{}_df.pkl'.format(OUTLET_NAME)))
            print('Done fetching stories from {} (outlet id = {}).'.format(OUTLET_NAME,curr_outlet_id))

    # Merge into a single df; filter out stories not in English; clean titles.
    dfs = []
    for filename in glob.glob('mediacloud/*.pkl'):
        df = pd.read_pickle(filename)
        dfs.append(df)
    df_all = pd.concat(dfs,ignore_index=True)
    df_all = df_all[df_all.language == 'en']
    df_all['clean_title'] = df_all.title.apply(lambda x: re.sub(r'[^a-zA-Z0-9\s]', '', x.lower()))
    df_all.to_pickle('mediacloud_df.pkl')

def get_serp_urls(domain_list=None):
    """
    Generates `google_search_res_climate_change_n.pkl`, a dictionary with outer keys for domains and inner keys for search terms.
    :param domain_list: list of domains. If None, will default to domains in `google_domains.txt`.
    """

    # Read in list of domains and political leanings for SerpAPI
    if domain_list is None:
        L_DOMAINS,R_DOMAINS = [],[]
        with open('google_domains.txt','r') as f:
            lines = f.readlines()
            for line in lines:
                split_line = line.split()
                R_DOMAINS.append(split_line[0]) if split_line[1] == 'R' else L_DOMAINS.append(split_line[0])
    else:
        L_DOMAINS = domain_list['L']
        R_DOMAINS = domain_list['R']

    # Initialize default nested dict with outer keys for each media domain and inner keys for each keyword.
    URLS_PER_DOMAIN = defaultdict(dict)

    # Query each domain for each keyword
    for DOMAIN in L_DOMAINS + R_DOMAINS:
        for KW in CC_KEYWORDS:
            dl = do_serpapi(DOMAIN,KW)
            results = parse_serpapi_results(dl)
            URLS_PER_DOMAIN[DOMAIN][KW] = results

    # Save nested dict
    existing = glob.glob('google_search_res_climate_change*')
    num_existing = len(existing)
    save_prefix = 'google_search_res_climate_change_{}'.format(num_existing)
    save_name = '{}.pkl'.format(save_prefix)
    print('Saving search results to {}...'.format(save_name))
    pickle.dump(URLS_PER_DOMAIN,open(save_name,'wb'))
    print('Done!')

def get_google_res_stance(x):
    """
    Returns pro- if L-wing, anti- if R-wing.
    :param x: a str URL.
    :return: str indicating outlet stance toward CC.
    """
    if 'foxnews.com' in x:
        return 'anti'
    elif 'breitbart.com' in x:
        return 'anti'
    elif 'blaze.com' in x:
        return 'anti'
    elif 'pjmedia.com' in x:
        return 'anti'
    elif 'nationalreview.com' in x:
        return 'anti'
    elif 'dailycaller.com' in x:
        return 'anti'
    elif 'reason.com' in x:
        return 'anti'
    elif 'americanthinker.com' in x:
        return 'anti'
    elif 'redstate.com' in x:
        return 'anti'
    elif 'infowars.com' in x:
        return 'anti'
    else:
        return 'pro'


def create_filtered_df():
    """Creates intermediate df for collected URLs, applying filtering, regularization, and deduplication."""

    BLACKLIST_URL_INIT_STRS = set(['rss.','feeds.','rssfeeds.'])
    def is_rss(url):
        """Determine if URL is from an RSS feed."""
        for xx in BLACKLIST_URL_INIT_STRS:
            if url[:len(xx)] == xx:
                return True
        return False

    with open('blacklist_url_tags.txt','r') as f:
        TAGS_TO_REMOVE = f.read().splitlines()

    def is_blacklist(url):
        """Helper function to determine if URL should be filtered out"""
        for xx in TAGS_TO_REMOVE:
            if xx in url:
                return True
        return False

    from urllib.parse import urlparse

    def get_hostname(url, uri_type='both'):
        """Get the host name from the url"""
        parsed_uri = urlparse(url)
        if uri_type == 'both':
            return '{uri.scheme}://{uri.netloc}/'.format(uri=parsed_uri)
        elif uri_type == 'netloc_only':
            return '{uri.netloc}'.format(uri=parsed_uri)

    def strip_url(url):
        """Strip leading 'http(s)://(www.) from URL'"""
        if url.startswith('http'):
            url = re.sub(r'https?://', '', url)
            #print(url)
        if url.startswith('www.'):
            url = re.sub(r'www.', '', url)
        return url

    def standardize_domain(x):
        if x == 'Guardian US':
            return 'guardian_us'
        elif 'washingtonpost.com' in x:
            return 'wapo'
        elif 'vox.com' in x:
            return 'vox'
        elif 'breitbart.com' in x:
            return 'breitbart'
        elif 'nytimes.com' in x:
            return 'nyt'
        elif 'motherjones.com' in x:
            return 'mj'
        elif x == 'democracy_now':
            return 'dem_now'
        elif 'foxnews.com' in x:
            return 'fox'
        elif 'buzzfeednews.com' in x or 'www.buzzfeed' in x:
            return 'buzzfeed'
        elif 'https://childrenshealthdefense.org/' in x:
            return 'chd'
        elif x == 'Daily Caller' or 'www.dailycaller' in x:
            return 'daily_caller'
        elif 'www.dailysignal' in x:
            return 'daily_signal'
        elif x == 'Washington Post':
            return 'wapo'
        elif 'theblaze.com' in x or x == 'the_blaze':
            return 'blaze'
        elif 'democracynow.org' in x:
            return 'dem_now'
        elif x == 'Grist':
            return 'grist'
        elif x == 'New York Times':
            return 'nyt'
        elif 'nationalreview.com' in x:
            return 'nat_review'
        elif 'thenation.com' in x:
            return 'nation'
        elif x == 'Breitbart':
            return 'breitbart'
        elif x == 'Christian Science Monitor':
            return 'cs_monitor'
        elif 'https://www.csmonitor/' in x:
            return 'cs_monitor'
        elif x == 'buzzfeed_news':
            return 'buzzfeed'
        elif x == 'washington_post':
            return 'wapo'
        elif x == 'FOX News':
            return 'fox'
        elif x == 'USA Today':
            return 'usa_today'
        elif x == 'Mother Jones':
            return 'mj'
        elif x == 'NBC News' or 'nbcnews.com' in x:
            return 'nbc'
        elif x == 'Democracy Now!':
            return 'dem_now'
        elif x == 'National Review':
            return 'nat_review'
        elif x == 'CNS News':
            return 'cns'
        elif x == 'Buzzfeed':
            return 'buzzfeed'
        elif x == 'The Nation':
            return 'nation'
        elif 'pjmedia.com' in x:
            return 'pj'
        elif 'pajamas_media' in x:
            return 'pj'
        elif x == 'pj' or x == 'pjmedia':
            return 'pj'
        elif 'www.americanthinker' in x:
            return 'american_thinker'
        elif 'www.redstate' in x:
            return 'redstate'
        elif 'www.infowars' in x:
            return 'infowars'
        elif 'www.wnd' in x:
            return 'wnd'
        elif 'www.nysun' in x:
            return 'new_york_sun'
        elif 'www.cnsnews' in x:
            return 'cns'
        elif 'www.realclearpolitics' in x:
            return 'real_clear_politics'
        elif 'www.newsmax' in x:
            return 'newsmax'
        elif 'www.newsbusters.org' in x:
            return 'newsbusters'
        elif 'www.unionleader' in x:
            return 'unionleader'
        elif 'www.townhall' in x:
            return 'townhall'
        elif 'www.hotair' in x:
            return 'hot_air'
        else:
            return x.lower().strip().replace(' ','_').replace('.com','')

    def standardize_date(x):
        if x is not None:
            if type(x) == str:
                x = x.replace('·','').strip()
                try:
                    return parser.parse(x)
                except ValueError:
                    #print(x)
                    return None
            elif type(x) == datetime.datetime:
                return x
            else:
                return x.to_pydatetime()

    # Create a dataframe combining all data structures with urls, that filters according to above criteria.
    filtered_urls = []
    filtered_titles = []
    filtered_dates = []
    filtered_domains = []
    filtered_stances = []
    filtered_topics = []
    filtered_is_AP = []

    google_cc_urls = pickle.load(open('google_search_res_climate_change.pkl','rb'))
    mediacloud_cc_urls = pd.read_pickle('mediacloud_df.pkl')

    for key in google_cc_urls:
        for keyword in google_cc_urls[key]:
            for item in google_cc_urls[key][keyword]:
                url = strip_url(item[1])
                if not is_rss(url) and not is_blacklist(url):
                    title = item[0]
                    date = item[2] if len(item) > 2 else None
                    stance = get_google_res_stance(url)
                    topic = 'cc'
                    is_AP = None

                    if ' | ' not in title:
                        filtered_urls.append(url)
                        filtered_titles.append(title)
                        filtered_dates.append(date)
                        filtered_domains.append(key)
                        filtered_stances.append(stance)
                        filtered_topics.append(topic)
                        filtered_is_AP.append(is_AP)

    for ix in mediacloud_cc_urls.index:
        row = mediacloud_cc_urls.loc[ix]
        url = strip_url(row['url']) if 'http' in row['url'] else strip_url(row['guid'])
        if not is_rss(url) and not is_blacklist(url):
            title = row['clean_title']
            date = row['publish_date']
            domain = row['media_name']
            stance = row['stance']
            topic = row['topic']
            is_AP = row['ap_syndicated']

            if ' | ' not in title:
                filtered_urls.append(url)
                filtered_titles.append(title)
                filtered_dates.append(date)
                filtered_domains.append(domain)
                filtered_stances.append(stance)
                filtered_topics.append(topic)
                filtered_is_AP.append(is_AP)

    combined_df = pd.DataFrame({'url':filtered_urls,
                              'title':filtered_titles,
                              'date':filtered_dates,
                              'domain':filtered_domains,
                              'stance':filtered_stances,
                              'topic':filtered_topics,
                              'is_AP':filtered_is_AP})
    combined_df['domain'] = combined_df.domain.apply(standardize_domain)
    combined_df.title = combined_df.title.apply(lambda x: x.strip().lower() if x
                                           is not None else x)
    stance_reg_dict = {'l':'pro','r':'anti','c':'between','pro':'pro','anti':'anti','between':'between'}
    combined_df = combined_df.loc[~pd.isnull(combined_df.stance)]
    combined_df['stance'] = combined_df.stance.apply(lambda x: stance_reg_dict[x])
    #combined_df.stance.value_counts()
    combined_df['date'] = combined_df['date'].apply(standardize_date)
    # We sort combined_df by title and date so that when we drop duplicate URLs,
    # we keep the one that doesn't have a null value for these fields.
    combined_df = combined_df.sort_values(['title'],axis=0)
    combined_df = combined_df.drop_duplicates(subset='url',keep='first')#,ignore_index=True)
    print('Intermediate df shape:',combined_df.shape)
    print('Saving intermediate df to "temp_combined_df.pkl"...')
    combined_df.to_pickle('temp_combined_df.pkl')

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_option('--domains', type=str, default=None,
                      help='/path/to/domains')

    args = parser.parse_args()

    print('Getting URLs...')
    if args.domains is not None:
        domain_dict = pickle.load(args.domains)
        get_serp_urls(domain_dict)
    else:
        get_serp_urls()
    get_mc_urls()
    print('Done retrieving URLs!')

    print('Creating intermediate dataframe...')
    create_filtered_df()
