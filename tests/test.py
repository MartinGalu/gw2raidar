from django.test import TestCase


class TestingSuiteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # set up data for whole test class
        cls.user = 'xunrise'

    def test_Simple(self):
        self.assertEqual(self.user, 'xunrise')
