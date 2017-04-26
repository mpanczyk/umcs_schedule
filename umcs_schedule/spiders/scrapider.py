import scrapy
from string import ascii_lowercase
from functools import partial
import re
import logging

logger = logging.getLogger('schedule')

class ScheduleSpider(scrapy.Spider):

    name = 'schedule'
    base_url = 'http://moria.umcs.lublin.pl'

    regex_table_type_num = re.compile(r'grid\/(\d+)\/')
    @staticmethod
    def table_type(url):
        match_object = ScheduleSpider.regex_table_type_num.search(url)
        if match_object:
            return int(match_object.group(1))

    def start_requests(self):
        urls = [
            self.base_url + '/link/',
        ]
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse_index)

    def parse_index(self, response):
        for letter in ascii_lowercase + 'ęóąśłżźćń0123456789':
            yield scrapy.Request(
                url=self.base_url + '/link/filtered/{}/0'.format(letter),
                callback=self.parse_list,
            )

    def parse_list(self, response):
        for url in response.css('a::attr(href)').extract():
            table_type = self.table_type(url)
            if table_type:
                method = self.parse_table_methods[table_type]
                yield scrapy.Request(
                    url=self.base_url + url,
                    callback=partial(method, self),
                )

    def style2dict(self, style):
        return dict(
            tuple(pair.split(': ', 1))
            for pair in style.split('; ')
            if pair
        )

    def parse_activity_block_style(self, style_str):
        style_attrs = self.style2dict(style_str)
        for key in style_attrs:
            value = style_attrs[key]
            if value.endswith('%'):
                style_attrs[key] = float(value[:-1])
        eps = 10**-5
        day = int(style_attrs['left']*.07+eps)
        one_nth = int(eps+1.0/(style_attrs['width']*0.07))
        start = int((21-8)*.01*60*style_attrs['top']+eps)+8*60
        duration = int(style_attrs['height']*(21-8)*.01*60+eps)
        end = start + duration
        return {
            'day': day,
            'start': start,
            'end': end,
            'one_nth': one_nth,
            'duration': duration,
        }

    def parse_activity_block(self, block, **kwargs):
        style = block.css('::attr(style)').extract_first()
        time = self.parse_activity_block_style(style)
        group_no = block.css('.activity_group ::text').extract_first()
        content = block.css('.activity_content')
        subject = content.css('.subject_content ::text').extract_first()
        teachers = [
            {
                'name': teacher.css('::text').extract_first(),
                'link': teacher.css('a::attr(href)').extract_first(),
            }
            for teacher in content.css('div.teachers_content div')
        ]
        year_groups = [
            {
                'name': yr_grp.css('::text').extract_first(),
                'link': yr_grp.css('a::attr(href)').extract_first(),
            }
            for yr_grp in content.css('div.students_content div')
        ]
        bottom_content = content.css('div.bottom_content_containter')
        room = {
            'name': bottom_content.css('div.room_content ::text').extract_first(),
            'link': bottom_content.css('div.room_content a::attr(href)').extract_first(),
        }
        type = bottom_content.css('div.type_content a::attr(title)').extract_first()
        type_short = bottom_content.css('div.type_content a::text').extract_first()
        ret_dict = {
            'group_no': group_no,
            'subject': subject,
            'teachers': teachers,
            'year_groups': year_groups,
            'time': time,
            'type': type,
            'type_short': type_short,
            'room': room,
        }
        ret_dict.update(kwargs)
        return ret_dict

    def link(self, url):
        if url.startswith(self.base_url):
            return url[len(self.base_url):]
        return url

    def parse_table_students(self, response):
        logger.debug('students table response: %s', response)
        header = self.get_header(response)
        students = {
            'name': header,
            'link': self.link(response.url),
        }
        for block in response.css('.activity_block'):
            yield self.parse_activity_block(block, year_groups=[students])

    def parse_table_teacher(self, response):
        logger.debug('teacher table response: %s', response)
        header = self.get_header(response)
        teacher = {
            'name': header,
            'link': self.link(response.url),
        }
        for block in response.css('.activity_block'):
            yield self.parse_activity_block(block, teachers=[teacher])

    def parse_table_classroom(self, response):
        logger.debug('classroom table response: %s', response)
        header = self.get_header(response)
        room = {
            'name': header,
            'link': self.link(response.url),
        }
        for block in response.css('.activity_block'):
            yield self.parse_activity_block(block, room=room)
            
    def get_header(self, response):
        return response.css('#plan_header a ::text').extract_first()

    parse_table_methods = {
        1: parse_table_students,
        2: parse_table_teacher,
        3: parse_table_classroom,
    }
