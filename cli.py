import argparse
import cmd, sys

import media.mbr as mbr
import media.gpt as gpt
import part.refs.vol as vol
import part.refs.entry_block as reb
import part.refs.tree_control as rtc
import part.refs.allocator as ralloc
import part.refs.object_tree as rot
import part.refs.attribute as rattr
from util.hexdump import hexdump
import carving

class PyReFSShell(cmd.Cmd):
    intro = None
    #     intro = '''Hello master! Welcome home.
    # I will try to help you to analyze your ReFS partition dumps.
    # Type 'help' or '?' to list commands.\n'''
    prompt = '> '
    rec_file = None
    dump_filename = None
    dump_file = None
    part = None
    parts = None
    blocks = None

    def preloop(self):
        print('''Hello master! Welcome home.
I will try to help you to analyze your ReFS partition dumps.
Type 'help' or '?' to list commands.''')
        if not self.dump_filename:
            print('''Master I just realized you haven't set a dump to analyze.
Please use the 'file' command to set it.''')

    def do_file(self, arg):
        '''Use the provided dump file for your deep analysis.
        I will try to automatically select the right partition for you.'''
        print('Loading {}'.format(arg))
        self.dump_filename = arg
        self.dump_file = open(self.dump_filename, 'rb')
        mbr_data = mbr.readMBR(self.dump_file)
        gpt_part = None
        for part_index, part in mbr_data:
            if part['ptype'] == mbr.MBR_PARTTYPE_GPT:
                gpt_part = part
                break
        if not gpt_part:
            print('ARGH Master. I couldn\'t find a GPT volume in the dump' +
                  ' you provided me. Please, try with another file.')
            self.dump_filename = None
            self.dump_file.close()
            self.dump_file = None
            return
        gpt_data = gpt.readGPT(self.dump_file, gpt_part['start'])
        parts = [ p for p in gpt_data['parts']
                  if p['type'] == gpt.GUID_PART_TYPE_W_BASIC_DATA_PART
                  and vol.is_refs_part(self.dump_file, p['first_lba']) ]
        if not parts:
            print('ARGH Master. I couldn\'t find a ReFS' +
                  ' partition in the dump file you provided.' +
                  ' Please, try with another file.',
                  gpt.GUID_TRANSLATION[gpt.GUID_PART_TYPE_W_BASIC_DATA_PART])
            self.dump_filename = None
            self.dump_file.close()
            self.dump_file = None
            return
        if len(parts) > 1:
            print(('Master, {} ReFS partitions were found.\n' +
                   'I will be using partition {}, but you can list the available' +
                   ' partitions and switch between them with the \'part\' command.').format(
                       len(parts), parts[0]['index']))
        self.parts = parts
        self.part = parts[0]
        print('Partition {} will be used.'.format(self.part['index']))
        gpt.print_gpt_part(self.part)
        self.prompt = '\n{} part {} - first lba: {} last lba: {}\n> '.format(
                self.dump_filename,
                self.part['index'],
                self.part['first_lba'],
                self.part['last_lba'])
        return

    def do_part(self, arg):
        '''Show available partitions ('part') and select from them ('part <partition index>').'''
        if not arg:
            print('Master you have {} partition{} available, here they are.'.format(
                len(self.parts), 's' if len(self.parts) > 1 else ''))
            for p in self.parts:
                gpt.print_gpt_part(self.part)
            return
        if int(arg) not in [ p['index'] for p in self.parts ]:
            print('Master I don\'t have the partition index {} you provided.'.format(
                arg))
            return
        if int(arg) == self.part['index']:
            print('Nothing done, as we are already using partition {}.'.format(
                arg))
            return
        self.part = self.parts[int(arg)]
        print('Switched to partition {}, enjoy Master.'.format(arg))
        self.prompt = '\n{} part {} - first lba: {} last lba: {}\n> '.format(
                self.dump_filename,
                self.part['index'],
                self.part['first_lba'],
                self.part['last_lba'])
        gpt.print_gpt_part(self.part)

    def do_find_blocks(self, arg):
        'Extract all the entry blocks.'
        offset = self.part['first_lba']
        end_offset = self.part['last_lba']
        if arg:
            if len(arg.split()) != 2:
                print('Master, two offsets are expected start and end.')
                return
            offset, end_offset = tuple(map(lambda x: int(x), arg.split()))
        if self.blocks == None:
            print(('Looking for blocks between lba {} and lba {}.' +
                   ' This may take a while Master. A coffee?').format(
                       offset,
                       end_offset))
            self.blocks = carving.find_blocks(self.dump_file, offset, end_offset)
        print('Master I found {} blocks.'.format(len(self.blocks)))
        carving.print_blocks(self.blocks)

    def do_find_blocks_with_filenames(self, arg):
        'Find which blocks have a file attribute.'
        if not self.blocks:
            print('Master, first you need to look for the blocks.')
            print('Please Master, use \'find_blocks\' first.')
            return
        blocks = carving.blocks_with_filename_attributes(self.dump_file, self.blocks) 
        print('Master I found {} blocks with the filename attribute.'.format(len(blocks)))
        carving.print_blocks(blocks)

    def do_find_blocks_with_folders(self, arg):
        'Find which blocks have a folder attribute.'
        if not self.blocks:
            print('Master, first you need to look for the blocks.')
            print('Please Master, use \'find_blocks\' first.')
            return
        blocks = carving.blocks_with_folder_attributes(self.dump_file, self.blocks) 
        print('Master I found {} blocks with the folder attribute.'.format(len(blocks)))
        carving.print_blocks(blocks)

    def do_list_filenames(self, arg):
        'List the found filenames from the list of blocks with filenames.'
        if not self.blocks:
            print('Master, first you need to look for the blocks and blocks with filenames.')
            print('Please Master, use \'find_blocks\' and \'find_blocks_with_filenames\' first.')
            return
        listed = 0
        for block in self.blocks:
            if block['fnas']:
                for fid in block['fnas']:
                    attr = rattr.read_attribute(self.dump_file, fid)
                    try:
                        filename = attr['filename'].decode('utf-16le')
                    except:
                        filename = attr['filename']
                    listed = listed + 1
                    print('{:#010x} {:#06x} {:#06x} {:#06x} {:#010x} {}'.format(
                        block['offset'], block['entryblock'],
                        block['nodeid'], block['childid'], attr['_absolute_offset'], filename))
        print('Master I listed {} folders.'.format(listed))
        if not listed:
            print('Master are you sure you performed \'find_blocks_with_folders\' before?')

    def do_list_folders(self, arg):
        'List the found folders from the list of blocks with folders.'
        if not self.blocks:
            print('Master, first you need to look for the blocks and blocks with folders.')
            print('Please Master, use \'find_blocks\' and \'find_blocks_with_folders\' first.')
            return
        listed = 0
        for block in self.blocks:
            if block['folderids']:
                for fid in block['folderids']:
                    attr = rattr.read_attribute(self.dump_file, fid)
                    try:
                        foldername = attr['foldername'].decode('utf-16le')
                    except:
                        foldername = attr['foldername']
                    listed = listed + 1
                    print('{:#010x} {:#06x} {:#06x} {:#06x} {:#010x} {}'.format(
                        block['offset'], block['entryblock'],
                        block['nodeid'], block['childid'], attr['_absolute_offset'], foldername))
        print('Master I listed {} folders.'.format(listed))
        if not listed:
            print('Master are you sure you performed \'find_blocks_with_folders\' before?')

    def do_hexdump(self, arg):
        'Hexdump size bytes of the provided offset.'
        if not arg or len(arg.split()) != 2:
            print('Please Master indicate the offset and the size of the hexdump.')
        args = [ int(x, 0) for x in arg.split() ]
        offset = args[0]
        size = args[1]
        self.dump_file.seek(offset, 0)
        data = self.dump_file.read(size)
        hexdump(data, offset)

    def do_hexblock(self, arg):
        'Hexdump the provided entryblock id.'
        if not arg:
            print('Please Master indicate the block to hexdump.')
            return
        if not self.blocks:
            print('Master, first you need to look for the blocks.')
            print('Please Master use \'find_blocks\' first.')
            return
        ebid = int(arg, 0)
        blks = [ b for b in self.blocks if b['entryblock'] == ebid ]
        if not blks:
            print('Master, are you sure such an entryblock exist?')
            return
        blk = blks[0]
        self.dump_file.seek(blk['offset'], 0)
        data = self.dump_file.read(16 * 1024)
        hexdump(data, blk['offset'])

    def do_entryblock(self, arg):
        'Dump a block as an entryblock.'
        if not arg:
            print('Please Master indicate the block to dump as entryblock.')
            return
        bid = int(arg, 0)
        if not self.blocks:
            print('Master, first you need to look for the blocks.')
            print('Please Master use \'find_blocks\' first.')
            return
        blocks = [ b for b in self.blocks if b['entryblock'] == bid ]
        if len(blocks) != 1:
            print('Master, I couldn\'t find the block you asked for.')
            return
        block = blocks[0]
        eb = reb.read_entryblock(self.dump_file, block['offset'])
        reb.dump_entryblock(eb)

    def do_tree_control(self, arg):
        'Dump a block as tree control.'
        if not arg:
            print('Please Master indicate the block to dump as tree control.')
            return
        bid = int(arg, 0)
        if not self.blocks:
            print('Master, first you need to look for the blocks.')
            print('Please Master use \'find_blocks\' first.')
            return
        blocks = [ b for b in self.blocks if b['entryblock'] == bid ]
        if len(blocks) != 1:
            print('Master, I couldn\'t find the block you asked for.')
            return
        block = blocks[0]
        tc = rtc.read_tree_control(self.dump_file, block['offset'])
        rtc.dump_tree_control(tc)

    def do_tree_control_extension(self, arg):
        'Dump a block as tree control extension.'
        if not arg:
            print('Please Master indicate the block to dump as tree control extension.')
            return
        bid = int(arg, 0)
        if not self.blocks:
            print('Master, first you need to look for the blocks.')
            print('Please Master use \'find_blocks\' first.')
            return
        blocks = [ b for b in self.blocks if b['entryblock'] == bid ]
        if len(blocks) != 1:
            print('Master, I couldn\'t find the block you asked for.')
            return
        block = blocks[0]
        tce = rtc.read_tree_control_ext(self.dump_file, block['offset'])
        rtc.dump_tree_control_ext(tce)

    def do_object_tree(self, arg):
        'Dump a block as object tree.'
        if not arg:
            print('Please Master indicate the block to dump as object tree.')
            return
        bid = int(arg, 0)
        if not self.blocks:
            print('Master, first you need to look for the blocks.')
            print('Please Master use \'find_blocks\' first.')
            return
        blocks = [ b for b in self.blocks if b['entryblock'] == bid ]
        if len(blocks) != 1:
            print('Master, I couldn\'t find the block you asked for.')
            return
        block = blocks[0]
        ot = rot.read_object_tree(self.dump_file, block['offset'])
        rot.dump_object_tree(ot)

    def do_allocator(self, arg):
        'Dump a block as allocator.'
        if not arg:
            print('Please Master indicate the block to dump as allocator.')
            return
        bid = int(arg, 0)
        if not self.blocks:
            print('Master, first you need to look for the blocks.')
            print('Please Master use \'find_blocks\' first.')
            return
        blocks = [ b for b in self.blocks if b['entryblock'] == bid ]
        if len(blocks) != 1:
            print('Master, I couldn\'t find the block you asked for.')
            return
        block = blocks[0]
        al = ralloc.read_allocator(self.dump_file, block['offset'])
        ralloc.dump_allocator(al)

    def do_attribute(self, arg):
        'Dump the attribute at the given offset.'
        if not arg:
            print('Please Master indicate the offset with the attribute to dump.')
            return
        offset = int(arg, 0)
        attr = rattr.read_attribute(self.dump_file, offset)
        rattr.dump_attribute(attr)

    def do_bye(self, arg):
        'Are you sure?'
        print('''It's been a great to serve you master.
Bye!!!!''')
        self.close()
        return True

    # ----- record and playback -----
    def do_record(self, arg):
        'Save future commands to filename:  RECORD rose.cmd'
        self.rec_file = open(arg, 'w')

    def do_playback(self, arg):
        'Playback commands from a file:  PLAYBACK rose.cmd'
        self.close()
        with open(arg) as f:
            self.cmdqueue.extend(f.read().splitlines())

    def precmd(self, line):
        line = line.lower()
        if self.rec_file and 'playback' not in line:
            print(line, file=self.rec_file)
        return line

    def close(self):
        if self.rec_file:
            self.rec_file.close()
            self.rec_file = None

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='ReFS carving on provided dump.')
    parser.add_argument('-d', '--dump', action='store', required=False, type=str,
                        help='ReFS dump to analyze')
    args = parser.parse_args()

    if args.dump:
        rshell = PyReFSShell()
        rshell.onecmd('file ' + args.dump)
        rshell.cmdloop()
    else:
        PyReFSShell().cmdloop()
