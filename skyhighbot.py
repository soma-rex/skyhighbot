import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from dotenv import load_dotenv
import sqlite3
from collections import defaultdict
import ast
import io
import textwrap
from contextlib import redirect_stdout


sniped_messages = defaultdict(list)
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True


bot = commands.Bot(command_prefix=";", intents=intents)
afk_users = {}
afk_mentions = {}




conn = sqlite3.connect("botdata.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS event_donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount TEXT,
    event_type TEXT,
    requirement TEXT,
    message TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS giveaway_donations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount TEXT,
    requirement TEXT,
    message TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# ---------- PREFIX COMMANDS ----------

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send("<:lock:1481008281538269365> Channel locked.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send("<:unlock:1481008283408924803> Channel unlocked.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def viewlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=False)
    await ctx.send("<:lock:1481008281538269365> Channel viewlocked.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unviewlock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, view_channel=True)
    await ctx.send("<:unlock:1481008283408924803> Channel unviewlocked.")

@bot.event
async def on_message_delete(message):

    if message.author.bot:
        return

    data = {
        "content": message.content,
        "author": message.author,
        "avatar": message.author.display_avatar.url
    }

    sniped_messages[message.channel.id].insert(0, data)

    if len(sniped_messages[message.channel.id]) > 10:
        sniped_messages[message.channel.id].pop()

# ---------- TIMER ----------

class ReminderView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.users = set()

    @discord.ui.button(label="Remind Me", emoji="<:timer:1481008388165865573>", style=discord.ButtonStyle.green)
    async def remind_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.users.add(interaction.user.id)
        await interaction.response.send_message(
            "<a:check:1481008329185558649> You will be reminded when the timer ends.",
            ephemeral=True
        )

class SnipeView(discord.ui.View):

    def __init__(self, ctx, messages):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.messages = messages
        self.index = 0

    def create_embed(self):

        msg = self.messages[self.index]

        embed = discord.Embed(
            description=msg["content"] or "*No text content*",
            color=discord.Color.random()
        )

        embed.set_author(
            name=str(msg["author"]),
            icon_url=msg["avatar"]
        )

        embed.set_footer(text=f"Message {self.index+1}/{len(self.messages)}")

        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):

        if self.index > 0:
            self.index -= 1

        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):

        if self.index < len(self.messages) - 1:
            self.index += 1

        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Delete All Snipes", style=discord.ButtonStyle.danger)
    async def clear(self, interaction: discord.Interaction, button: discord.ui.Button):

        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message(
                "<a:cross:1481008346818674718> Only admins can delete snipes.",
                ephemeral=True
            )

        sniped_messages[self.ctx.channel.id].clear()

        embed = discord.Embed(
            description="🗑️ All sniped messages have been deleted.",
            color=discord.Color.random()
        )

        await interaction.response.edit_message(embed=embed, view=None)

@bot.tree.command(name="timer", description="Start a timer")
@app_commands.describe(
    hours="Hours (optional)",
    minutes="Minutes",
    seconds="Seconds (optional)"
)
async def timer(
    interaction: discord.Interaction,
    minutes: int,
    hours: int = 0,
    seconds: int = 0
):

    total_seconds = hours * 3600 + minutes * 60 + seconds

    view = ReminderView()

    embed = discord.Embed(
        title="<:timer:1481008388165865573> Timer Started",
        description=f"Timer set for **{hours}h {minutes}m {seconds}s**.\n\nClick **Remind Me** to get pinged.",
        color=discord.Color.orange()
    )

    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)

    embed.set_footer(
        text=f"Started by {interaction.user}",
        icon_url=interaction.user.display_avatar.url
    )

    await interaction.response.send_message(embed=embed, view=view)

    await asyncio.sleep(total_seconds)

    if view.users:
        mentions = " ".join(f"<@{u}>" for u in view.users)

        msg = await interaction.channel.send(
            f"<:timer:1481008388165865573> Timer finished!\n{mentions}"
        )

        await asyncio.sleep(5)
        await msg.delete()

    else:
        await interaction.channel.send("<:timer:1481008388165865573> Timer finished!")

# ---------- EVENT PING ----------

@bot.tree.command(name="eping", description="Ping an event")
async def eping(
    interaction: discord.Interaction,
    prize: str,
    role: discord.Role,
    event_type: str,
    requirement: str = None,
    message: str = None,
    donor: str = None
):

    embed = discord.Embed(
        title="<a:event:1481008273816686632> Event Started",
        color=discord.Color.green()
    )

    embed.add_field(name="Prize", value=prize, inline=False)
    embed.add_field(name="Event Type", value=event_type, inline=False)

    if requirement:
        embed.add_field(name="Requirement", value=requirement, inline=False)

    if donor:
        embed.add_field(name="Donor", value=donor, inline=False)

    if message:
        embed.add_field(name="Message", value=message, inline=False)

    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)

    embed.set_footer(
        text=f"Hosted by {interaction.user}",
        icon_url=interaction.user.display_avatar.url
    )

    await interaction.response.send_message(
        content=role.mention,
        embed=embed
    )

# ---------- GIVEAWAY PING ----------

@bot.tree.command(name="gping", description="Ping a giveaway")
async def gping(
    interaction: discord.Interaction,
    prize: str,
    role: discord.Role,
    requirement: str = None,
    message: str = None,
    donor: str = None
):

    embed = discord.Embed(
        title="<a:giveaway:1481008279487250604> Giveaway",
        color=discord.Color.gold()
    )

    embed.add_field(name="Prize", value=prize, inline=False)

    if requirement:
        embed.add_field(name="Requirement", value=requirement, inline=False)

    if donor:
        embed.add_field(name="Donor", value=donor, inline=False)

    if message:
        embed.add_field(name="Message", value=message, inline=False)

    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)

    embed.set_footer(
        text=f"Hosted by {interaction.user}",
        icon_url=interaction.user.display_avatar.url
    )

    await interaction.response.send_message(
        content=role.mention,
        embed=embed
    )
# ---------- DONATION PROMPTS ----------


@bot.tree.command(name="edonate", description="Donate for an event")
async def edonate(
    interaction: discord.Interaction,
    amount: str,
    event_type: str,
    message: str = None,
    requirement: str = None
):

    allowed_channel = 1395496725007044700

    if interaction.channel.id != allowed_channel:
        return await interaction.response.send_message(
            "<a:cross:1481008346818674718> This command can only be used in the event donation channel.",
            ephemeral=True
        )

    role = interaction.guild.get_role(1034819411103727658)

    # SAVE TO DATABASE
    cursor.execute("""
        INSERT INTO event_donations (user_id, amount, event_type, requirement, message)
        VALUES (?, ?, ?, ?, ?)
    """, (
        interaction.user.id,
        amount,
        event_type,
        requirement,
        message
    ))

    conn.commit()

    embed = discord.Embed(
        title="<a:moneythrow:1481013626629259435> Event Donation",
        color=discord.Color.blue()
    )

    embed.add_field(name="Amount", value=amount, inline=False)
    embed.add_field(name="Event Type", value=event_type, inline=False)

    if requirement:
        embed.add_field(name="Requirement", value=requirement, inline=False)

    if message:
        embed.add_field(name="Message", value=message, inline=False)

    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)

    embed.set_footer(
        text=f"Donated by {interaction.user}, Thank you for your donation!",
        icon_url=interaction.user.display_avatar.url
    )

    await interaction.response.send_message(
        content=role.mention,
        embed=embed
    )
@bot.tree.command(name="gdonate", description="Donate for a giveaway")
async def gdonate(
    interaction: discord.Interaction,
    amount: str,
    message: str = None,
    requirement: str = None
):

    allowed_channel = 1034819412601098314

    if interaction.channel.id != allowed_channel:
        return await interaction.response.send_message(
            "<a:cross:1481008346818674718> This command can only be used in the <#1034819412601098314>.",
            ephemeral=True
        )

    role = interaction.guild.get_role(1034827940535488612)

    # SAVE TO DATABASE
    cursor.execute("""
        INSERT INTO giveaway_donations (user_id, amount, requirement, message)
        VALUES (?, ?, ?, ?)
    """, (
        interaction.user.id,
        amount,
        requirement,
        message
    ))

    conn.commit()

    embed = discord.Embed(
        title="<a:moneythrow:1481013626629259435> Giveaway Donation",
        color=discord.Color.purple()
    )

    embed.add_field(name="Amount", value=amount, inline=False)

    if requirement:
        embed.add_field(name="Requirement", value=requirement, inline=False)

    if message:
        embed.add_field(name="Message", value=message, inline=False)

    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)

    embed.set_footer(
        text=f"Donated by {interaction.user}, Thank you for your donation!",
        icon_url=interaction.user.display_avatar.url
    )

    await interaction.response.send_message(
        content=role.mention,
        embed=embed
    )
class GenderRoles(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # LEFT SPACER (disabled)
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer1(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    # HE/HIM ROLE
    @discord.ui.button(emoji="<:male:1482313910584475669>", style=discord.ButtonStyle.secondary)
    async def hehim(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819410982096994)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                f"<a:cross:1481008346818674718> Role **{role.name}** removed.",
                ephemeral=True
            )
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"<a:check:1481008329185558649> Role **{role.name}** added.",
                ephemeral=True
            )

    # SHE/HER ROLE
    @discord.ui.button(emoji="<:female:1482313908701102110>", style=discord.ButtonStyle.secondary)
    async def sheher(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819410982096993)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                f"<a:cross:1481008346818674718> Role **{role.name}** removed.",
                ephemeral=True
            )
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"<a:check:1481008329185558649> Role **{role.name}** added.",
                ephemeral=True
            )

    # THEY/THEM ROLE
    @discord.ui.button(emoji="<:theythem:1482313912035573761>", style=discord.ButtonStyle.secondary)
    async def theythem(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819410982096992)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                f"<a:cross:1481008346818674718> Role **{role.name}** removed.",
                ephemeral=True
            )
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"<a:check:1481008329185558649> Role **{role.name}** added.",
                ephemeral=True
            )

    # RIGHT SPACER (disabled)
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer2(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass
class AgeRoles(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # BUTTON 1 (disabled spacer)
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer1(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    # UNDER 18
    @discord.ui.button(emoji="<:under18:1482313905115234357>", style=discord.ButtonStyle.secondary)
    async def under18(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819410982096989)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                f"<a:cross:1481008346818674718> Role **{role.name}** removed.",
                ephemeral=True
            )
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"<a:check:1481008329185558649> Role **{role.name}** added.",
                ephemeral=True
            )

    # BUTTON 3 (disabled spacer)
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer2(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    # 18+
    @discord.ui.button(emoji="<a:above18:1482313978704298037>", style=discord.ButtonStyle.secondary)
    async def over18(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819410982096990)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(
                f"<a:cross:1481008346818674718> Role **{role.name}** removed.",
                ephemeral=True
            )
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(
                f"<a:check:1481008329185558649> Role **{role.name}** added.",
                ephemeral=True
            )

    # BUTTON 5 (disabled spacer)
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer3(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

class ServerPings(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # ROW 1 LEFT SPACER
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer1(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    # ANNOUNCEMENT PING
    @discord.ui.button(emoji="<a:announce:1482330492089925746>", style=discord.ButtonStyle.secondary)
    async def announcement(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819411007242265)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # CHAT REVIVE
    @discord.ui.button(emoji="<:chatrevive:1482330499845460048>", style=discord.ButtonStyle.secondary)
    async def revive(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819411007242260)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # PARTNERSHIP
    @discord.ui.button(emoji="<a:partner:1482330517796950119>", style=discord.ButtonStyle.secondary)
    async def partnership(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819411007242262)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # ROW 1 RIGHT SPACER
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer2(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass


    # ROW 2 LEFT SPACER
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer3(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    # NO PARTNERSHIP
    @discord.ui.button(emoji="<a:nopartner:1482330515972427899>", style=discord.ButtonStyle.secondary)
    async def nopartner(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1342436846784876624)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # CASINO PING
    @discord.ui.button(emoji="<a:casino:1482330497584726036>", style=discord.ButtonStyle.secondary)
    async def casino(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1407344106711154698)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # SLEEPY NEWSPAPER
    @discord.ui.button(emoji="<:newspaper:1482330512918843513>", style=discord.ButtonStyle.secondary)
    async def news(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1453123314070323221)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # ROW 2 RIGHT SPACER
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer4(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

class DankPings(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    # ROW 1 LEFT SPACER
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer1(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    # HEIST
    @discord.ui.button(emoji="<a:heist:1482330509592760432>", style=discord.ButtonStyle.secondary)
    async def heist(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819411007242261)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # EVENTS
    @discord.ui.button(emoji="<a:events:1482330505113374830>", style=discord.ButtonStyle.secondary)
    async def events(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819411007242266)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # GIVEAWAYS
    @discord.ui.button(emoji="<a:giveaway:1481008279487250604>", style=discord.ButtonStyle.secondary)
    async def giveaways(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819411007242268)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # ROW 1 RIGHT SPACER
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer2(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass


    # ROW 2 LEFT SPACER
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer3(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    # FLASH GIVEAWAYS
    @discord.ui.button(emoji="<a:lightning:1482330511279132712>", style=discord.ButtonStyle.secondary)
    async def flash(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1341409546379329617)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # RUMBLE
    @discord.ui.button(emoji="<a:rumbl:1482330521492131971>", style=discord.ButtonStyle.secondary)
    async def rumble(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1034819411007242263)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # AUCTION
    @discord.ui.button(emoji="<:auction:1482330495411949669>", style=discord.ButtonStyle.secondary)
    async def auction(self, interaction: discord.Interaction, button: discord.ui.Button):

        role = interaction.guild.get_role(1478109554742005791)

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"<a:cross:1481008346818674718> Role **{role.name}** removed.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"<a:check:1481008329185558649> Role **{role.name}** added.", ephemeral=True)

    # ROW 2 RIGHT SPACER
    @discord.ui.button(label="\u200b", style=discord.ButtonStyle.secondary, disabled=True)
    async def spacer4(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

@bot.command()
async def dankpings(ctx):

    embed = discord.Embed(
        title="<a:dankpingsemoji:1482330502034620527> │ Dank Pings",
        description="Select which Dank Memer notifications you want!",
        color=discord.Color.from_rgb(154,128,127)
    )

    embed.add_field(
        name="Available Roles",
        value="""
<a:heist:1482330509592760432> **<@&1034819411007242261>**
<a:events:1482330505113374830> **<@&1034819411007242266>**
<a:giveaway:1481008279487250604> **<@&1034819411007242268>**
<a:lightning:1482330511279132712> **<@&1341409546379329617>**
<a:rumbl:1482330521492131971> **<@&1034819411007242263>**
<:auction:1482330495411949669> **<@&1478109554742005791>**
""",
        inline=False
    )

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.set_image(url="https://media.discordapp.net/attachments/1455004091829719092/1482326856589119569/dankpingforservergif.gif?ex=69b68bf6&is=69b53a76&hm=572447cfe66fb2e43bc12283bead9baa5a488f1d4a4237126bac47059aff3b51&=&width=747&height=417")

    await ctx.send(embed=embed, view=DankPings())

@bot.command()
async def genderroles(ctx):

    embed = discord.Embed(
        title="<a:genderrolesemoji:1482314714510921881> │ Gender Roles",
        description="Get your desired roles!!",
        color=discord.Color.from_rgb(154,128,127)
    )

    embed.add_field(
        name="Available Roles",
        value="""
<:male:1482313910584475669> **<@&1034819410982096994>**
<:female:1482313908701102110> **<@&1034819410982096993>**
<:theythem:1482313912035573761> **<@&1034819410982096992>**
""",
        inline=False
    )

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.set_image(url="https://cdn.discordapp.com/attachments/1455004091829719092/1481048596508836011/pronouns-gender.gif?ex=69b1e57d&is=69b093fd&hm=9da1b72c0d15e3fac6469f6d5ff287e3fb6c389e9e507734cd9a8595a2514ea9&")

    await ctx.send(embed=embed, view=GenderRoles())

@bot.command()
async def ageroles(ctx):

    embed = discord.Embed(
        title="<a:agerolesemoji:1482314712573018256> │ Age Roles",
        description="Select your age category!",
        color=discord.Color.from_rgb(154,128,127)
    )

    embed.add_field(
        name="Available Roles",
        value="""
<:under18:1482313905115234357> **<@&1034819410982096989>**
<a:above18:1482313978704298037> **<@&1034819410982096990>**
""",
        inline=False
    )

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.set_image(url="https://media.discordapp.net/attachments/1455004091829719092/1482312448684851210/ageroles.gif?ex=69b67e8b&is=69b52d0b&hm=a21727671aaab463b2f05f90afcc3714f52823a84567f61d02bafecdbefd8c25&=&width=747&height=417")

    await ctx.send(embed=embed, view=AgeRoles())

@bot.command()
async def serverpings(ctx):

    embed = discord.Embed(
        title="<a:serverpingsemoji:1482330523459129416> │ Server Pings",
        description="Select which notifications you want!",
        color=discord.Color.from_rgb(154,128,127)
    )

    embed.add_field(
        name="Available Roles",
        value="""
<a:announce:1482330492089925746> **<@&1034819411007242265>**
<:chatrevive:1482330499845460048> **<@&1034819411007242260>**
<a:partner:1482330517796950119> **<@&1034819411007242262>**
<a:nopartner:1482330515972427899> **<@&1342436846784876624>**
<a:casino:1482330497584726036> **<@&1407344106711154698>**
<:newspaper:1482330512918843513> **<@&1453123314070323221>**
""",
        inline=False
    )

    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)

    embed.set_image(url="https://media.discordapp.net/attachments/1455004091829719092/1482324371027787807/gifforserverpingroles-ezgif.com-added-text.gif?ex=69b689a6&is=69b53826&hm=78a7e951728538f1b95527d481f3f5eb02d412a079ee1c3057103cc12a2b79de&=&width=747&height=423")

    await ctx.send(embed=embed, view=ServerPings())

@bot.command()
async def afk(ctx, *, reason="No reason provided"):

    allowed_roles = [1391628882150690826, 1034819411057594505]

    if not any(role.id in allowed_roles for role in ctx.author.roles):
        return await ctx.send("<a:cross:1481008346818674718> You cannot use this command.")

    afk_users[ctx.author.id] = reason
    afk_mentions[ctx.author.id] = []

    # change nickname
    try:
        await ctx.author.edit(nick=f"[AFK] {ctx.author.display_name}")
    except:
        pass

    embed = discord.Embed(
        title="<a:sleep:1482433784300441700> AFK Enabled",
        description=f"{ctx.author.mention} is now AFK",
        color=discord.Color.random()
    )

    embed.add_field(name="Reason", value=reason)

    await ctx.send(embed=embed)


@bot.command(name="eval")
@commands.is_owner()
async def eval_cmd(ctx: commands.Context, *, code: str):

    await ctx.message.delete()

    def cleanup_code(content: str):
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:-1])
        return content.strip("` \n")

    code = cleanup_code(code)

    try:
        ast.parse(code, mode="eval")
    except SyntaxError:
        body = code
    else:
        body = f"return {code}"

    env = {
        "bot": bot,
        "ctx": ctx,
        "discord": discord,
        "commands": commands,
        "cursor": cursor,
        "conn": conn,
        "asyncio": asyncio
    }

    env.update(globals())

    stdout = io.StringIO()

    to_compile = f"async def func():\n{textwrap.indent(body, '    ')}"

    try:
        exec(to_compile, env)
    except Exception:
        return await ctx.send("undefined")

    func = env["func"]

    try:
        with redirect_stdout(stdout):
            result = await func()
    except Exception:
        return await ctx.send("undefined")

    value = stdout.getvalue().rstrip()

    if result is None:
        if value:
            await ctx.send(f"```py\n{value}\n```")
        else:
            await ctx.send("undefined")
        return

    await ctx.send(f"```py\n{result}\n```")

# ---------- READY EVENT ----------

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    # AFK user returns
    if message.author.id in afk_users:

        mentions = afk_mentions.get(message.author.id, [])

        try:
            if message.author.nick and message.author.nick.startswith("[AFK] "):
                await message.author.edit(nick=message.author.nick.replace("[AFK] ", ""))
        except:
            pass

        embed = discord.Embed(
            title="<a:wave:1482433781603504148> Welcome Back",
            description=f"{message.author.mention} is no longer AFK.",
            color=discord.Color.random()
        )

        if mentions:
            links = "\n".join(mentions[:20])
            embed.add_field(name="You were pinged here:", value=links, inline=False)
        else:
            embed.add_field(name="Mentions", value="No one pinged you while AFK.")

        await message.channel.send(embed=embed)

        del afk_users[message.author.id]
        del afk_mentions[message.author.id]

    # Someone mentions AFK user
    for user in message.mentions:

        if user.id in afk_users:

            reason = afk_users[user.id]

            afk_mentions[user.id].append(message.jump_url)

            embed = discord.Embed(
                description=f"<a:sleep:1482433784300441700> {user.mention} is currently **AFK**",
                color=discord.Color.random()
            )

            embed.add_field(name="Reason", value=reason)

            await message.channel.send(embed=embed)

    await bot.process_commands(message)

@bot.command()
async def snipe(ctx):

    allowed_roles = [1391628882150690826, 1034819411057594505]

    if not any(role.id in allowed_roles for role in ctx.author.roles):
        return await ctx.send("<a:cross:1481008346818674718> You do not have permission to use this command.")

    messages = sniped_messages.get(ctx.channel.id)

    if not messages:
        return await ctx.send("<a:cross:1481008346818674718> Nothing to snipe.")

    view = SnipeView(ctx, messages)

    await ctx.send(embed=view.create_embed(), view=view)

@bot.tree.command(name="ping", description="Check the bot latency")
async def ping(interaction: discord.Interaction):

    latency = round(bot.latency * 1000)

    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latency: **{latency} ms**",
        color=discord.Color.green()
    )

    embed.set_footer(
        text=f"Requested by {interaction.user}",
        icon_url=interaction.user.display_avatar.url
    )

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="help", description="View all bot commands")
async def help_cmd(interaction: discord.Interaction):

    embed = discord.Embed(
        title="🤖 Bot Commands",
        description="Here are all available commands.",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="<:lock:1481008281538269365> Moderation",
        value="""
`/lock`
`/unlock`
`/viewlock`
`/unviewlock`
""",
        inline=False
    )

    embed.add_field(
        name="⚙️ Utility",
        value="""
`/ping`
`/help`
`/timer`
`/snipe`
`/afk`
""",
        inline=False
    )

    embed.add_field(
        name="<a:events:1482330505113374830> Events",
        value="""
`/eping`
`/gping`
""",
        inline=False
    )

    embed.add_field(
        name="<a:moneythrow:1481013626629259435> Donations",
        value="""
`/edonate`
`/gdonate`
""",
        inline=False
    )

    embed.set_footer(
        text=f"Requested by {interaction.user}",
        icon_url=interaction.user.display_avatar.url
    )

    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)
