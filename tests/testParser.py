import logging
import os

from django.test import TestCase
from evtcparser import parser
from zipfile import ZipFile

TEST_DIRECTORY = './tests/testLogs'


class ParserTest(TestCase):
    @classmethod
    def setUpTestData(cls):

        cls.user = 'xunrise'
        cls.testFiles = []
        print("Finding test files: \n")
        for filename in os.listdir(TEST_DIRECTORY):
            if filename.endswith(".zevtc"):
                cls.testFiles.append(os.path.join(TEST_DIRECTORY, filename))
                print(filename)

    def test_setupComplete(self):
        self.assertEqual(self.user, 'xunrise')
        self.assertGreater(len(self.testFiles), 0)

    def test_singleFile(self):
        filename = self.testFiles[0]
        self.parseEncounter(filename)

    def test_AllFiles(self):
        for filename in self.testFiles:
            self.parseEncounter(filename)

    def parseEncounter(self, filename):
        if filename.endswith(".zip") or filename.endswith(".zevtc"):
            zipfile = ZipFile(filename)
            contents = zipfile.infolist()
            if len(contents) == 1:
                file = zipfile.open(contents[0].filename)
        else:
            file = open(filename)
        firstenc = parser.Encounter(file)
        self.assertIsNotNone(firstenc)
        players = firstenc.agents[firstenc.agents['account'] != -1]
        self.assertGreater(len(players), 0)
        self.assertLessEqual(len(players), 50)
        print(players)
