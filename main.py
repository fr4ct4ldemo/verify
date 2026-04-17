import asyncio
import uuid
import threading
import time
import requests
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Config
from database import Database


class VerificationBot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = Database()
        self.cleanup_task.start()
        self.check_verified_task.start()
        self.kick_unverified_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()
        self.check_verified_task.cancel()
        self.kick_unverified_task.cancel()

    # API Helpers for Vercel communication
    def create_web_verification(self, user_id: int) -> str:
        """Create verification on web server and return the URL."""
        try:
            response = requests.post(
                f"{Config.BASE_URL}/api/verification/{user_id}",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('url', '')
        except Exception as e:
            print(f"Error creating web verification: {e}")
        return None

    def get_web_verified_users(self) -> list:
        """Get list of verified users from web server."""
        try:
            response = requests.get(
                f"{Config.BASE_URL}/api/verified",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('verified_users', [])
        except Exception as e:
            print(f"Error getting verified users: {e}")
        return []

    def delete_web_verification(self, user_id: int):
        """Delete verification from web server."""
        try:
            requests.delete(
                f"{Config.BASE_URL}/api/check/{user_id}",
                timeout=10
            )
        except Exception as e:
            print(f"Error deleting web verification: {e}")

    # Embed Helpers
    def create_embed(
        self,
        title: str,
        description: str = None,
        color: int = Config.COLOR_INFO,
        fields: list = None,
        footer: str = None
    ) -> discord.Embed:
        """Create a consistent embed."""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.utcnow()
        )
        if fields:
            for field in fields:
                embed.add_field(
                    name=field.get('name', ''),
                    value=field.get('value', ''),
                    inline=field.get('inline', False)
                )
        if footer:
            embed.set_footer(text=footer)
        return embed

    # Log to channel
    async def log_event(
        self,
        guild: discord.Guild,
        event_type: str,
        user: discord.Member = None,
        user_id: int = None,
        extra: str = None
    ):
        """Log events to the configured log channel."""
        settings = self.db.get_server_settings(guild.id)
        if not settings or not settings.get('log_channel_id'):
            return

        log_channel = guild.get_channel(settings['log_channel_id'])
        if not log_channel:
            return

        user_mention = user.mention if user else f"<@{user_id}>"
        user_id_val = user.id if user else user_id

        color_map = {
            'user_joined': Config.COLOR_INFO,
            'verification_sent': Config.COLOR_INFO,
            'verification_success': Config.COLOR_SUCCESS,
            'verification_failed': Config.COLOR_ERROR,
            'verification_timeout': Config.COLOR_WARNING,
            'verification_lockout': Config.COLOR_ERROR,
            'user_kicked': Config.COLOR_ERROR
        }

        embed = self.create_embed(
            title=f"Verification {event_type.replace('_', ' ').title()}",
            color=color_map.get(event_type, Config.COLOR_INFO),
            fields=[
                {"name": "User", "value": user_mention, "inline": True},
                {"name": "User ID", "value": str(user_id_val), "inline": True},
                {"name": "Action", "value": event_type.replace('_', ' ').title(), "inline": True}
            ]
        )
        if extra:
            embed.add_field(name="Details", value=extra, inline=False)

        await log_channel.send(embed=embed)

    # Send DM Embed
    async def send_dm_embed(
        self,
        user: discord.User,
        title: str,
        description: str = None,
        color: int = Config.COLOR_INFO,
        fields: list = None,
        components: list = None
    ) -> bool:
        """Send an embed DM to a user."""
        try:
            embed = self.create_embed(
                title=title,
                description=description,
                color=color,
                fields=fields
            )
            await user.send(embed=embed, components=components)
            return True
        except discord.Forbidden:
            return False

    # Verification Button
    def create_verify_button(self, token: str) -> discord.ui.Button:
        """Create verification button."""
        return discord.ui.Button(
            label="Verify",
            style=discord.ButtonStyle.link,
            url=f"{Config.BASE_URL}/verify?token={token}",
            emoji="🛡️"
        )

    def create_verify_button_from_url(self, url: str) -> discord.ui.Button:
        """Create verification button from full URL."""
        return discord.ui.Button(
            label="Verify",
            style=discord.ButtonStyle.link,
            url=url,
            emoji="🛡️"
        )

    # Start Verification
    async def start_verification(self, user: discord.Member, guild: discord.Guild):
        """Start a new verification session for a user."""
        settings = self.db.get_server_settings(guild.id)
        if not settings or not settings.get('verified_role_id'):
            return

        # Check if already locked out
        if self.db.is_locked_out(user.id):
            remaining = self.db.get_lockout_remaining(user.id)
            minutes = int(remaining / 60) + 1
            await self.send_dm_embed(
                user,
                title="⏰ Temporarily Locked Out",
                description=f"You are currently locked out due to too many failed attempts.",
                color=Config.COLOR_ERROR,
                fields=[
                    {"name": "Try Again", "value": f"Please try again in {minutes} minute(s).", "inline": False}
                ]
            )
            return

        # Check if expired and clean up
        if self.db.is_expired(user.id):
            self.db.delete_verification(user.id)

        # Create new verification session
        token = str(uuid.uuid4())
        self.db.create_verification(user.id, token, Config.VERIFICATION_TIMEOUT)

        # Also create on web server (for Vercel deployment)
        web_url = self.create_web_verification(user.id)
        if web_url:
            token = web_url.split('token=')[1] if 'token=' in web_url else token
            verification_url = web_url
        else:
            verification_url = f"{Config.BASE_URL}/verify?token={token}"

        # Send DM with verification button
        view = discord.ui.View()
        view.add_item(self.create_verify_button_from_url(verification_url))

        await self.send_dm_embed(
            user,
            title="🛡️ Discord Verification",
            description="Welcome! Please complete verification to access the server.",
            color=Config.COLOR_INFO,
            fields=[
                {"name": "Instructions", "value": "Click the button below to complete hCaptcha verification.", "inline": False},
                {"name": "⏱️ Time Limit", "value": "You have 10 minutes to complete verification.", "inline": True},
                {"name": "🔄 Attempts", "value": "You have 3 attempts per session.", "inline": True}
            ],
            components=view
        )

        await self.log_event(guild, 'verification_sent', user)

    # Verify User (called from web server)
    async def verify_user(self, user_id: int, guild: discord.Guild):
        """Verify a user and assign the verified role."""
        user = guild.get_member(user_id)
        if not user:
            return

        settings = self.db.get_server_settings(guild.id)
        if not settings:
            return

        verified_role = guild.get_role(settings['verified_role_id'])
        if not verified_role:
            return

        try:
            await user.add_roles(verified_role)
            self.db.delete_verification(user_id)

            await self.send_dm_embed(
                user,
                title="✅ Verification Successful!",
                description="You have been verified and now have access to the server.",
                color=Config.COLOR_SUCCESS,
                fields=[
                    {"name": "Welcome!", "value": f"You now have access to {guild.name}. Enjoy!", "inline": False}
                ]
            )

            await self.log_event(guild, 'verification_success', user)
        except discord.Forbidden:
            await self.send_dm_embed(
                user,
                title="❌ Verification Error",
                description="There was an error assigning your role. Please contact an admin.",
                color=Config.COLOR_ERROR
            )

    # Handle Member Join
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle new member joins."""
        guild = member.guild
        settings = self.db.get_server_settings(guild.id)

        if not settings or not settings.get('verified_role_id'):
            return

        await self.start_verification(member, guild)
        await self.log_event(guild, 'user_joined', member)

    # Cleanup Task
    @tasks.loop(minutes=1)
    async def cleanup_task(self):
        """Clean up expired verification sessions."""
        # Clean up expired from database
        cleaned = self.db.cleanup_expired()
        if cleaned > 0:
            print(f"Cleaned up {cleaned} expired verification sessions")

    # Check Verified Task - polls web server for completed verifications
    @tasks.loop(seconds=5)
    async def check_verified_task(self):
        """Check for users who have completed verification."""
        for guild in self.bot.guilds:
            settings = self.db.get_server_settings(guild.id)
            if not settings or not settings.get('verified_role_id'):
                continue

            verified_role = guild.get_role(settings['verified_role_id'])
            if not verified_role:
                continue

            # Get newly verified users from web server (Vercel) or local DB
            try:
                verified_users = self.get_web_verified_users()
            except:
                # Fallback to local database if web server unavailable
                verified_users = self.db.get_newly_verified()

            for user_id in verified_users:
                user = guild.get_member(user_id)
                if user and verified_role not in user.roles:
                    try:
                        await user.add_roles(verified_role)
                        
                        await self.send_dm_embed(
                            user,
                            title="✅ Verification Successful!",
                            description="You have been verified and now have access to the server.",
                            color=Config.COLOR_SUCCESS,
                            fields=[
                                {"name": "Welcome!", "value": f"You now have access to {guild.name}. Enjoy!", "inline": False}
                            ]
                        )
                        
                        await self.log_event(guild, 'verification_success', user)
                        self.db.delete_verification(user_id)
                        self.delete_web_verification(user_id)
                    except discord.Forbidden:
                        pass

    # Kick Unverified Task
    @tasks.loop(minutes=1)
    async def kick_unverified_task(self):
        """Kick unverified users after the timer expires."""
        for guild in self.bot.guilds:
            settings = self.db.get_server_settings(guild.id)
            if not settings or not settings.get('kick_unverified'):
                continue

            if not settings.get('verified_role_id'):
                continue

            kick_timer = settings.get('kick_timer', 30)
            verified_role = guild.get_role(settings['verified_role_id'])
            if not verified_role:
                continue

            # Check members without verified role
            for member in guild.members:
                if verified_role in member.roles:
                    continue

                # Check if member has a pending verification
                verification = self.db.get_verification(member.id)
                if not verification:
                    # No verification, might be new - skip for now
                    continue

                # Check if expired
                if self.db.is_expired(member.id):
                    # Send timeout message
                    await self.send_dm_embed(
                        member,
                        title="⏰ Verification Session Expired",
                        description="Your verification link has expired.",
                        color=Config.COLOR_ERROR,
                        fields=[
                            {"name": "What to do", "value": "Use `/verify` in the server to get a new verification link.", "inline": False}
                        ]
                    )
                    
                    await self.log_event(guild, 'verification_timeout', member)
                    self.db.delete_verification(member.id)

                    # Kick if enabled
                    try:
                        await member.kick(reason="Failed to verify within time limit")
                        await self.log_event(guild, 'user_kicked', member)
                    except discord.Forbidden:
                        pass

    # Slash Commands
    @app_commands.command(name="verify", description="Start or restart verification")
    async def verify(self, interaction: discord.Interaction):
        """Start verification process."""
        user = interaction.user
        guild = interaction.guild

        settings = self.db.get_server_settings(guild.id)
        if not settings or not settings.get('verified_role_id'):
            await interaction.response.send_message(
                embed=self.create_embed(
                    title="⚙️ Verification Not Configured",
                    description="Verification has not been set up on this server yet.",
                    color=Config.COLOR_ERROR
                ),
                ephemeral=True
            )
            return

        # Check if user already has the verified role
        verified_role = guild.get_role(settings['verified_role_id'])
        if verified_role in user.roles:
            await interaction.response.send_message(
                embed=self.create_embed(
                    title="✅ Already Verified",
                    description="You are already verified on this server.",
                    color=Config.COLOR_SUCCESS
                ),
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)
        await self.start_verification(user, guild)

        await interaction.followup.send(
            embed=self.create_embed(
                title="📨 Verification Sent",
                description="Check your DMs for the verification link!",
                color=Config.COLOR_SUCCESS
            ),
            ephemeral=True
        )

    @app_commands.command(name="setup", description="Configure verification settings (Admin only)")
    @app_commands.default_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        verified_role: discord.Role = None,
        log_channel: discord.TextChannel = None,
        kick_unverified: bool = False,
        kick_timer: int = 30
    ):
        """Setup verification for the server."""
        guild = interaction.guild

        # Get current settings
        current = self.db.get_server_settings(guild.id)

        # Update settings
        verified_role_id = verified_role.id if verified_role else (current.get('verified_role_id') if current else None)
        log_channel_id = log_channel.id if log_channel else (current.get('log_channel_id') if current else None)

        self.db.set_server_settings(
            guild.id,
            verified_role_id=verified_role_id,
            log_channel_id=log_channel_id,
            kick_unverified=kick_unverified,
            kick_timer=kick_timer
        )

        # Build response fields
        fields = []
        if verified_role:
            fields.append({"name": "✅ Verified Role", "value": verified_role.mention, "inline": True})
        if log_channel:
            fields.append({"name": "📝 Log Channel", "value": log_channel.mention, "inline": True})
        
        fields.append({"name": "🚪 Kick Unverified", "value": "Enabled" if kick_unverified else "Disabled", "inline": True})
        fields.append({"name": "⏱️ Kick Timer", "value": f"{kick_timer} minutes", "inline": True})

        await interaction.response.send_message(
            embed=self.create_embed(
                title="⚙️ Verification Settings",
                description="Server verification has been configured:",
                color=Config.COLOR_SUCCESS,
                fields=fields
            ),
            ephemeral=True
        )


# Bot Setup
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = app_commands.CommandTree(bot)


@bot.event
async def on_ready():
    """Bot is ready."""
    print(f"Bot logged in as {bot.user}")
    await tree.sync()
    print("Commands synced")


# Start the bot
def run_bot():
    """Run the Discord bot."""
    if not Config.validate():
        print("Please configure your .env file before running the bot.")
        return

    bot.add_cog(VerificationBot(bot))
    bot.run(Config.DISCORD_TOKEN)


if __name__ == "__main__":
    run_bot()